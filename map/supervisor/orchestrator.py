"""Main orchestrator: runs agents and gates progress at human checkpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from map.agents.base import BaseAgent
from map.comms.base import CommsRouter
from map.session.state import Checkpoint, Session, SessionStore, Subtask, Task
from map.supervisor.task_parser import build_planner_subtask

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    checkpoint_after_review: bool = False
    checkpoint_timeout_secs: float | None = None


@dataclass
class Orchestrator:
    """Drives the full pipeline loop for a single session."""

    store: SessionStore
    router: CommsRouter
    agents: dict[str, BaseAgent]
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)

    async def run(self, description: str, repo_path: str, context: str | None = None) -> Session:
        """Start a new session and run the full pipeline."""
        task = Task(description=description, repo_path=repo_path)
        session = Session(task=task)
        await self.store.save_session(session)
        await self._execute(session, context=context)
        return session

    async def resume(self, session_id: str) -> Session:
        """Reload a paused session and continue from its pending checkpoint."""
        session = await self.store.load_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id!r} not found")
        if session.status == "done":
            logger.info("Session %s is already done", session_id)
            return session
        await self._execute(session)
        return session

    async def _execute(self, session: Session, context: str | None = None) -> None:
        try:
            # Resolve any pending checkpoint first (resume path)
            pending_cp = session.pending_checkpoint
            if pending_cp is not None:
                approved = await self._resolve_checkpoint(pending_cp, session)
                if not approved:
                    session.status = "failed"
                    await self.store.save_session(session)
                    return
            # Run (or continue) the idempotent pipeline
            await self._run_pipeline(session, context=context)
        except Exception as exc:
            logger.error("Session %s failed: %s", session.id, exc)
            session.status = "failed"
            await self.store.save_session(session)
            raise

    async def _run_pipeline(self, session: Session, context: str | None = None) -> None:
        """Run or resume the pipeline, skipping already-completed steps."""

        def completed_output(agent: str) -> dict[str, Any] | None:
            for st in session.subtasks:
                if st.agent == agent and st.status == "done":
                    return st.output
            return None

        def checkpoint_done(cp_type: str) -> bool:
            return any(cp.type == cp_type and cp.is_resolved for cp in session.checkpoints)

        # --- Step 1: Plan ---
        plan = completed_output("planner")
        if plan is None:
            planner_subtask = build_planner_subtask(session, context=context)
            plan = await self._run_subtask(planner_subtask, session)

        # --- Checkpoint 1: Plan approval ---
        if not checkpoint_done("plan_approval"):
            approved = await self._checkpoint(
                session,
                cp_type="plan_approval",
                message=self._format_plan(plan),
            )
            if not approved:
                session.status = "failed"
                await self.store.save_session(session)
                return

        # --- Step 2: Implement ---
        impl_result = completed_output("implementer")
        if impl_result is None:
            impl_subtask = Subtask(
                session_id=session.id,
                agent="implementer",
                input={"plan": plan, "repo_path": session.task.repo_path},
            )
            session.subtasks.append(impl_subtask)
            impl_result = await self._run_subtask(impl_subtask, session)

        # --- Step 3: Review ---
        review_result = completed_output("reviewer")
        if review_result is None:
            review_subtask = Subtask(
                session_id=session.id,
                agent="reviewer",
                input={"impl": impl_result, "repo_path": session.task.repo_path},
            )
            session.subtasks.append(review_subtask)
            review_result = await self._run_subtask(review_subtask, session)

        # --- Optional Checkpoint 2: Review results ---
        review_passed = review_result.get("passed", True)
        if (self.config.checkpoint_after_review or not review_passed) and not checkpoint_done(
            "review_results"
        ):
            approved = await self._checkpoint(
                session,
                cp_type="review_results",
                message=self._format_review(review_result),
            )
            if not approved:
                session.status = "failed"
                await self.store.save_session(session)
                return

        # --- Step 4: Test ---
        test_result = completed_output("tester")
        if test_result is None:
            test_subtask = Subtask(
                session_id=session.id,
                agent="tester",
                input={"repo_path": session.task.repo_path},
            )
            session.subtasks.append(test_subtask)
            test_result = await self._run_subtask(test_subtask, session)

        # --- Checkpoint 3: Commit approval ---
        if not checkpoint_done("commit_approval"):
            approved = await self._checkpoint(
                session,
                cp_type="commit_approval",
                message=self._format_commit_summary(impl_result, review_result, test_result),
            )
            if not approved:
                session.status = "failed"
                await self.store.save_session(session)
                return

        session.status = "done"
        await self.store.save_session(session)
        logger.info("Session %s completed successfully", session.id)

    async def _run_subtask(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        agent = self.agents.get(subtask.agent)
        if agent is None:
            raise ValueError(f"No agent registered for role: {subtask.agent!r}")

        subtask.status = "running"
        await self.store.save_subtask(subtask)

        try:
            output = await agent.run(subtask, session)
            subtask.output = output
            subtask.status = "done"
        except Exception as exc:
            subtask.status = "failed"
            await self.store.save_subtask(subtask)
            raise RuntimeError(f"Agent {subtask.agent!r} failed: {exc}") from exc

        await self.store.save_subtask(subtask)
        return output

    async def _checkpoint(self, session: Session, cp_type: str, message: str) -> bool:
        cp = Checkpoint(session_id=session.id, type=cp_type, message=message)
        session.checkpoints.append(cp)
        session.status = "paused_at_checkpoint"
        await self.store.save_session(session)
        await self.store.save_checkpoint(cp)

        await self.router.send(message)
        return await self._resolve_checkpoint(cp, session)

    async def _resolve_checkpoint(self, cp: Checkpoint, session: Session) -> bool:
        from datetime import datetime, timezone

        reply = await self.router.wait_for_reply(timeout_secs=self.config.checkpoint_timeout_secs)
        if reply is None:
            logger.warning("Checkpoint %s timed out", cp.type)
            return False

        cp.response = reply
        cp.resolved_at = datetime.now(timezone.utc)
        session.status = "running"
        await self.store.save_checkpoint(cp)
        await self.store.save_session(session)

        normalized = reply.strip().lower()
        return normalized in {"yes", "y", "approve", "approved", "ok", "go", "proceed"}

    @staticmethod
    def _format_plan(plan: dict[str, Any]) -> str:
        lines = ["MAP CHECKPOINT: Plan Approval", ""]
        lines.append(f"Summary: {plan.get('summary', 'N/A')}")
        lines.append("")
        lines.append("Steps:")
        for step in plan.get("steps", []):
            lines.append(
                f"  {step.get('id', '?')}. [{step.get('agent', '?')}] {step.get('description', '')}"
            )
        lines.append("")
        lines.append("Reply 'approve' to proceed or 'reject' to cancel.")
        return "\n".join(lines)

    @staticmethod
    def _format_review(review: dict[str, Any]) -> str:
        lines = ["MAP CHECKPOINT: Review Results", ""]
        status = "PASSED" if review.get("passed") else "FAILED"
        lines.append(f"Status: {status}")
        if review.get("comments"):
            lines.append("")
            lines.append("Comments:")
            for comment in review["comments"]:
                lines.append(f"  - {comment}")
        lines.append("")
        lines.append("Reply 'approve' to continue or 'reject' to cancel.")
        return "\n".join(lines)

    @staticmethod
    def _format_commit_summary(
        impl: dict[str, Any], review: dict[str, Any], test: dict[str, Any]
    ) -> str:
        lines = ["MAP CHECKPOINT: Commit Approval", ""]
        if impl.get("diff"):
            lines.append("Diff summary:")
            lines.append(impl["diff"][:500])
            lines.append("")
        review_status = "PASSED" if review.get("passed") else "FAILED"
        test_status = "PASSED" if test.get("passed") else "FAILED"
        lines.append(f"Review: {review_status} | Tests: {test_status}")
        lines.append("")
        lines.append("Reply 'approve' to commit or 'reject' to cancel.")
        return "\n".join(lines)
