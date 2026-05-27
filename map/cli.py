"""MAP CLI entry point: map run / status / resume / sessions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

app = typer.Typer(
    name="map",
    help="Multi-Agent Pipeline — run coding tasks with human-in-the-loop checkpoints.",
    no_args_is_help=True,
)


def _build_orchestrator(config_path: str | None = None) -> tuple:
    """Construct the orchestrator and session store from config."""
    import anthropic

    from map.agents.implementer import ImplementerAgent
    from map.agents.planner import PlannerAgent
    from map.agents.reviewer import ReviewerAgent
    from map.agents.tester import TesterAgent
    from map.comms.base import CommsRouter
    from map.comms.terminal import TerminalCommunicator
    from map.config import Config
    from map.supervisor.orchestrator import OrchestratorConfig
    from map.tools.claude_code import ClaudeCodeRunner

    config = Config.load(config_path)

    if not config.anthropic_api_key:
        typer.echo("Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.")
        raise typer.Exit(1)

    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)

    client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    runner = ClaudeCodeRunner(default_tools=config.agents.implementer_tools)

    agents = {
        "planner": PlannerAgent(client=client, model=config.model.default),
        "implementer": ImplementerAgent(runner=runner, tools=config.agents.implementer_tools),
        "reviewer": ReviewerAgent(client=client, model=config.model.default),
        "tester": TesterAgent(runner=runner, tools=config.agents.tester_tools),
    }

    channels = [TerminalCommunicator()]
    if "telegram" in config.comms.channels and config.telegram_bot_token:
        from map.comms.telegram import TelegramCommunicator

        channels.append(
            TelegramCommunicator(
                token=config.telegram_bot_token,
                allowed_chat_id=config.telegram_allowed_chat_id,
            )
        )

    router = CommsRouter(channels)
    orch_config = OrchestratorConfig(
        checkpoint_after_review=config.pipeline.checkpoint_after_review,
        checkpoint_timeout_secs=config.pipeline.checkpoint_timeout_secs,
    )

    return config, router, agents, orch_config


@app.command()
def run(
    task: str = typer.Argument(..., help="Task description (quoted string)"),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to the target repository"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to map.yaml"),
) -> None:
    """Start a new pipeline session for TASK in REPO."""

    async def _run() -> None:
        from map.session.state import SessionStore
        from map.supervisor.orchestrator import Orchestrator

        cfg, router, agents, orch_config = _build_orchestrator(config)
        store = await SessionStore.open(cfg.db_path)
        try:
            orch = Orchestrator(store=store, router=router, agents=agents, config=orch_config)
            session = await orch.run(task, str(Path(repo).resolve()))
            typer.echo(f"\nSession {session.id}: {session.status.upper()}")
        finally:
            await store.close()

    asyncio.run(_run())


@app.command()
def resume(
    session_id: str = typer.Argument(..., help="Session ID to resume"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to map.yaml"),
) -> None:
    """Resume a paused session (e.g. after replying via Telegram)."""

    async def _resume() -> None:
        from map.session.state import SessionStore
        from map.supervisor.orchestrator import Orchestrator

        cfg, router, agents, orch_config = _build_orchestrator(config)
        store = await SessionStore.open(cfg.db_path)
        try:
            orch = Orchestrator(store=store, router=router, agents=agents, config=orch_config)
            session = await orch.resume(session_id)
            typer.echo(f"\nSession {session.id}: {session.status.upper()}")
        finally:
            await store.close()

    asyncio.run(_resume())


@app.command()
def status(
    session_id: str = typer.Argument(..., help="Session ID to inspect"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to map.yaml"),
) -> None:
    """Show the status of a session."""

    async def _status() -> None:
        from map.config import Config
        from map.session.state import SessionStore

        cfg = Config.load(config)
        store = await SessionStore.open(cfg.db_path)
        try:
            session = await store.load_session(session_id)
            if session is None:
                typer.echo(f"Session {session_id!r} not found.")
                raise typer.Exit(1)
            typer.echo(f"Session:  {session.id}")
            typer.echo(f"Task:     {session.task.description}")
            typer.echo(f"Repo:     {session.task.repo_path}")
            typer.echo(f"Status:   {session.status}")
            typer.echo(f"Subtasks: {len(session.subtasks)}")
            for st in session.subtasks:
                typer.echo(f"  [{st.status:8}] {st.agent}")
            if session.checkpoints:
                typer.echo("Checkpoints:")
                for cp in session.checkpoints:
                    resolved = "v" if cp.is_resolved else "pending"
                    typer.echo(f"  [{resolved}] {cp.type}")
        finally:
            await store.close()

    asyncio.run(_status())


@app.command(name="sessions")
def list_sessions(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to map.yaml"),
) -> None:
    """List recent sessions."""

    async def _list() -> None:
        from map.config import Config
        from map.session.state import SessionStore

        cfg = Config.load(config)
        store = await SessionStore.open(cfg.db_path)
        try:
            sessions = await store.list_sessions(limit=limit)
            if not sessions:
                typer.echo("No sessions found.")
                return
            typer.echo(f"{'ID':36}  {'STATUS':24}  TASK")
            typer.echo("-" * 80)
            for s in sessions:
                task_preview = s.task.description[:40]
                typer.echo(f"{s.id}  {s.status:24}  {task_preview}")
        finally:
            await store.close()

    asyncio.run(_list())
