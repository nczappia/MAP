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
    context: str | None = typer.Option(
        None,
        "--context",
        "-x",
        help="Path to a file with additional context (spec, design doc, constraints).",
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to map.yaml"),
) -> None:
    """Start a new pipeline session for TASK in REPO."""
    context_text: str | None = None
    if context is not None:
        ctx_path = Path(context)
        if not ctx_path.exists():
            typer.echo(f"Error: context file {context!r} not found.")
            raise typer.Exit(1)
        context_text = ctx_path.read_text()

    async def _run() -> None:
        from map.session.state import SessionStore
        from map.supervisor.orchestrator import Orchestrator

        cfg, router, agents, orch_config = _build_orchestrator(config)
        store = await SessionStore.open(cfg.db_path)
        try:
            orch = Orchestrator(store=store, router=router, agents=agents, config=orch_config)
            session = await orch.run(task, str(Path(repo).resolve()), context=context_text)
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


@app.command(name="help")
def help_cmd() -> None:
    """Print a detailed guide covering setup, usage, and how the pipeline works."""
    typer.echo(
        """
MAP — Multi-Agent Pipeline
==========================

MAP runs a coding task through a chain of specialized AI agents, pausing at key moments
to ask you (via terminal or Telegram) whether to proceed.

─────────────────────────────────────────────────────────────
QUICK START
─────────────────────────────────────────────────────────────

  1. Install
       pip install -e ".[dev]"

  2. Configure secrets
       cp .env.example .env
       # Set ANTHROPIC_API_KEY at minimum.
       # For Telegram: set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID.

  3. (Optional) Tune pipeline behaviour
       cp map.yaml.example map.yaml

  4. Run a task
       map run "add a hello-world function to main.py" --repo /path/to/repo

─────────────────────────────────────────────────────────────
COMMANDS
─────────────────────────────────────────────────────────────

  map run "<task>" [--repo PATH] [--config FILE]
      Start a new pipeline session.
      --repo   Target git repository (default: current directory).
      --config Path to a custom map.yaml (default: ./map.yaml).

  map resume <SESSION_ID> [--config FILE]
      Continue a session that was paused at a checkpoint (e.g. after a process
      restart or a Telegram reply arriving while the host was offline).

  map status <SESSION_ID>
      Show agents run, their statuses, and all checkpoints for a session.

  map sessions [--limit N]
      List the N most recent sessions (default 20).

  map help
      Print this guide.

  Any command also accepts --help for a short usage summary.

─────────────────────────────────────────────────────────────
HOW THE PIPELINE WORKS
─────────────────────────────────────────────────────────────

  Each run creates a Session stored in SQLite (~/.map/sessions.db).
  The session persists through restarts — use `map resume` to continue.

  Pipeline stages, in order:

  1. PLAN
     The Planner agent (Anthropic SDK) reads the task and produces a structured
     list of implementation steps with assigned agents.

  2. ── CHECKPOINT: Plan Approval ──
     MAP sends the plan to you (terminal + any configured remote channel).
     Reply: approve / yes / ok  →  continue
            reject / no          →  session marked failed, nothing written to disk

  3. IMPLEMENT
     The Implementer agent (Claude Code CLI subprocess) edits files in the repo
     according to the plan, using real file-system tools (Edit, Write, Bash, Read).

  4. REVIEW
     The Reviewer agent (Anthropic SDK) reads the diff and returns a pass/fail
     verdict with comments.
     If the review fails (or checkpoint_after_review: true in map.yaml), MAP
     pauses for a Review Results checkpoint so you can decide whether to proceed.

  5. TEST
     The Tester agent (Claude Code CLI subprocess) runs the test suite and reports
     pass/fail.

  6. ── CHECKPOINT: Commit Approval ──
     MAP sends the diff summary and test results.
     Reply: approve  →  git commit (and optionally open a PR if auto_open_pr: true)
            reject   →  session marked failed, working-tree changes left in place

─────────────────────────────────────────────────────────────
REMOTE CHECKPOINTS (TELEGRAM)
─────────────────────────────────────────────────────────────

  When Telegram is configured, checkpoint messages are sent to your phone and you
  can reply from anywhere — no need to be on the host machine.

  Setup:
    1. Create a bot via @BotFather on Telegram → copy the token.
    2. Start a chat with your bot, then fetch your chat ID:
         curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
    3. Add to .env:
         TELEGRAM_BOT_TOKEN=<token>
         TELEGRAM_ALLOWED_CHAT_ID=<your_chat_id>
    4. Enable in map.yaml:
         comms:
           channels:
             - terminal
             - telegram

  Whichever channel (terminal or Telegram) receives a reply first unblocks the
  checkpoint; the other is cancelled.

─────────────────────────────────────────────────────────────
CONFIGURATION (map.yaml)
─────────────────────────────────────────────────────────────

  pipeline:
    checkpoint_after_review: false   # pause after every review, not just failures
    auto_open_pr: false              # open a GitHub PR after commit
    checkpoint_timeout_secs: null    # seconds before a checkpoint auto-fails (null = wait forever)

  comms:
    channels:
      - terminal                     # always available
      - telegram                     # requires TELEGRAM_BOT_TOKEN in .env

  agents:
    implementer_tools:               # Claude Code CLI tool allowlist
      - Edit
      - Write
      - Bash
      - Read
    tester_tools:
      - Bash
      - Read

  model:
    default: claude-sonnet-4-6

─────────────────────────────────────────────────────────────
RESUMING AFTER AN INTERRUPTION
─────────────────────────────────────────────────────────────

  If the process dies while waiting at a checkpoint:
    1. Find the session: map sessions
    2. Resume it:        map resume <SESSION_ID>

  MAP re-sends the pending checkpoint message and continues from where it stopped.
  Completed agent steps are never re-run.
"""
    )


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
