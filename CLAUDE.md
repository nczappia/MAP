# MAP — Multi-Agent Pipeline

Hierarchical Python pipeline that accepts a coding task, decomposes it into subtasks, routes
them through specialized agents, and gates progress at human-in-the-loop checkpoints. Checkpoints
can be reached remotely via Telegram (and in future: SMS, email, Slack).

## Package layout

```
map/
  cli.py            — Typer entry point: map run / status / resume / sessions
  config.py         — layered config (.env → map.yaml → CLI flags)
  supervisor/
    orchestrator.py — main async loop + checkpoint gating
    task_parser.py  — LLM call to decompose task → ordered subtasks
  agents/
    base.py         — abstract BaseAgent
    planner.py      — Anthropic SDK
    implementer.py  — Claude Code CLI subprocess
    reviewer.py     — Anthropic SDK
    tester.py       — Claude Code CLI subprocess
  comms/
    base.py         — abstract Communicator + CommsRouter
    terminal.py     — stdin/stdout
    telegram.py     — python-telegram-bot v21
  session/
    state.py        — Session/Subtask/Checkpoint dataclasses + SQLite persistence
  tools/
    claude_code.py  — async subprocess wrapper for `claude --print`
    git.py          — git diff / commit / PR helpers
```

## Development setup

```bash
pip install -e ".[dev]"
pre-commit install
cp .env.example .env        # fill in ANTHROPIC_API_KEY at minimum
cp map.yaml.example map.yaml
```

## Running tests

```bash
pytest                      # unit + integration, with coverage
pytest tests/unit/          # unit only (faster)
pytest tests/integration/   # integration only
```

## Code quality

```bash
ruff check map/ tests/      # lint
ruff format map/ tests/     # format
mypy map/                   # type check
```

Pre-commit hooks run ruff + mypy automatically before every `git commit`.

## Key design rules

- **Never hardcode terminal I/O in the orchestrator.** All human communication goes through
  `CommsRouter`, which broadcasts to all configured `Communicator` instances.
- **Agents are stateless per invocation.** State lives in `Session` (SQLite-backed).
- **Planner + Reviewer use Anthropic SDK.** Implementer + Tester use Claude Code CLI subprocess
  (`tools/claude_code.py`) because they need real file access and tool use.
- **Sessions are resumable.** `map resume <id>` reloads from SQLite and re-sends any pending
  checkpoint message.
