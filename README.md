# MAP — Multi-Agent Pipeline

MAP runs a coding task through a chain of specialized AI agents, pausing at key moments to ask
you whether to proceed. Checkpoints can be reached from anywhere — terminal, Telegram, or (in
future) SMS, email, or Slack.

```
map run "add a login endpoint" --repo /path/to/repo
```

---

## Table of contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Providing context to agents](#providing-context-to-agents)
- [Commands](#commands)
- [Configuration reference](#configuration-reference)
- [Remote checkpoints via Telegram](#remote-checkpoints-via-telegram)
- [Resuming after an interruption](#resuming-after-an-interruption)
- [Development](#development)

---

## How it works

Each run creates a **Session** persisted in SQLite (`~/.map/sessions.db`). The pipeline is
fully resumable — if the process dies mid-wait, `map resume <id>` picks up exactly where it
left off.

```
map run "your task" --repo /path/to/repo
         │
    1.  PLAN
         Planner (Anthropic SDK) reads the task and any context you provide,
         then produces an ordered list of implementation steps.
         │
    ──── CHECKPOINT: Plan Approval ────────────────────────────────────
         MAP sends the plan to your terminal (and/or Telegram).
         Reply: approve / yes / ok  →  continue
                reject / no          →  session fails, nothing written to disk
    ───────────────────────────────────────────────────────────────────
         │
    2.  IMPLEMENT
         Implementer (Claude Code CLI) edits the repo files directly
         using real tools: Edit, Write, Bash, Read.
         │
    3.  REVIEW
         Reviewer (Anthropic SDK) inspects the diff — returns pass/fail
         + comments. If the review fails (or checkpoint_after_review: true
         in map.yaml), MAP pauses for a Review Results checkpoint.
         │
    4.  TEST
         Tester (Claude Code CLI) runs the test suite and reports pass/fail.
         │
    ──── CHECKPOINT: Commit Approval ──────────────────────────────────
         MAP sends the diff + test results.
         Reply: approve  →  git commit (+ optional PR)
                reject   →  session fails, changes left in working tree
    ───────────────────────────────────────────────────────────────────
```

**Agent split:** Planner and Reviewer use the Anthropic SDK (pure reasoning, no file access
needed). Implementer and Tester use the Claude Code CLI subprocess because they need real file
system access and tool use.

---

## Installation

Requires Python 3.10+.

```bash
git clone <this-repo>
cd MAP
pip install -e ".[dev]"
```

---

## Quick start

```bash
# 1. Configure secrets
cp .env.example .env
#    Open .env and set ANTHROPIC_API_KEY at minimum.

# 2. (Optional) tune pipeline behaviour
cp map.yaml.example map.yaml

# 3. Run a task
map run "add a hello-world function to main.py" --repo /path/to/repo
```

MAP will print the plan and wait for your approval in the terminal before touching any files.

---

## Providing context to agents

The task description alone is often enough for simple changes, but for anything non-trivial you
should give the agents more to work with. There are two complementary ways to do this.

### 1. `--context` flag (recommended for per-run specs)

Pass a file containing any extra information: a design spec, architectural constraints,
acceptance criteria, links to related code, things NOT to change, etc.

```bash
map run "implement the auth middleware" \
    --repo /path/to/repo \
    --context docs/auth-spec.md
```

The file contents are included verbatim in the Planner's prompt, so everything you write
there directly shapes the plan and all subsequent agent steps.

**Example context file (`auth-spec.md`):**

```markdown
## Constraints
- Use the existing `flask_jwt_extended` library already in requirements.txt — no new deps.
- The middleware must live in `app/middleware/auth.py`.
- Do not touch `app/routes/public.py` — those endpoints are intentionally unauthenticated.

## Acceptance criteria
- All existing tests in `tests/test_auth.py` must still pass.
- New endpoints decorated with `@requires_auth` must return 401 for missing/invalid tokens.
- Add at least one test for the 401 case.

## Related files
- `app/models/user.py` — User model, use `User.get_by_id()` for token validation.
- `app/config.py` — JWT secret is already loaded as `app.config["JWT_SECRET"]`.
```

### 2. `CLAUDE.md` in your repo (recommended for standing project conventions)

The Implementer and Tester agents use the Claude Code CLI, which automatically reads a
`CLAUDE.md` at the repo root. Put your project-wide conventions there:

```markdown
# My Project

## Tech stack
Python 3.11, FastAPI, SQLAlchemy, pytest.

## Conventions
- All routes live in `app/routes/`, one file per resource.
- Tests mirror the source tree under `tests/`.
- Never use `print()` — use the `logger` from `app.logging`.
- All database queries go through the repository layer in `app/repos/`.
```

**Tip:** Use both together. `CLAUDE.md` carries permanent project rules; `--context` carries
per-task specifics.

---

## Commands

```
map run "<task>" [--repo PATH] [--context FILE] [--config FILE]
```
Start a new pipeline session. `--repo` defaults to the current directory.

```
map resume <SESSION_ID> [--config FILE]
```
Continue a session that was paused at a checkpoint (e.g. after a process restart or a Telegram
reply arriving while the host was offline).

```
map status <SESSION_ID>
```
Show the agents run, their statuses, and all checkpoints for a session.

```
map sessions [--limit N]
```
List the N most recent sessions (default 20).

```
map help
```
Print the full in-terminal guide.

Every command also accepts `--help` for a short usage summary.

---

## Configuration reference

Copy `map.yaml.example` to `map.yaml` and edit as needed.

```yaml
pipeline:
  # Pause for human review after every reviewer pass, not just failures.
  checkpoint_after_review: false

  # Open a GitHub PR automatically after commit (requires `gh` CLI auth).
  auto_open_pr: false

  # Seconds before a checkpoint auto-fails. null = wait forever.
  checkpoint_timeout_secs: null

comms:
  channels:
    - terminal      # always available — stdin/stdout
    - telegram      # enable if TELEGRAM_BOT_TOKEN is set in .env

agents:
  # Tools the Implementer is allowed to call via Claude Code CLI.
  implementer_tools:
    - Edit
    - Write
    - Bash
    - Read
  tester_tools:
    - Bash
    - Read

model:
  default: claude-sonnet-4-6
```

Secrets go in `.env` (never committed):

```bash
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...          # optional
TELEGRAM_ALLOWED_CHAT_ID=...    # optional
```

---

## Remote checkpoints via Telegram

With Telegram configured, checkpoint messages arrive on your phone and you can approve or
reject from anywhere — no need to be on the host machine.

```
map run "refactor the auth module" --repo /repo
  → sends plan to your phone
  → you reply "approve" from the Telegram app
  → pipeline continues
```

**Setup:**

1. Open Telegram and message `@BotFather` → `/newbot` → copy the bot token.

2. Start a chat with your new bot, then run:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   ```
   Find `"chat": {"id": <number>}` in the response — that is your chat ID.

3. Add to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_ALLOWED_CHAT_ID=<your_chat_id>
   ```

4. Enable in `map.yaml`:
   ```yaml
   comms:
     channels:
       - terminal
       - telegram
   ```

Whichever channel (terminal or Telegram) receives a reply first unblocks the pipeline; the
other is cancelled. Approved words: `approve`, `yes`, `y`, `ok`, `go`, `proceed`.

---

## Resuming after an interruption

Sessions are stored in SQLite and survive process restarts. If MAP dies while waiting at a
checkpoint:

```bash
# Find the session
map sessions

# Resume — MAP re-sends the pending checkpoint and continues
map resume <SESSION_ID>
```

Completed agent steps are never re-run on resume.

---

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Install pre-commit hooks (ruff + mypy run before every commit)
pre-commit install

# Run tests
pytest                   # unit + integration, with coverage report
pytest tests/unit/       # unit only (faster)
pytest tests/integration/

# Lint and format
ruff check map/ tests/
ruff format map/ tests/

# Type check
mypy map/
```

CI runs on every push and pull request: lint → format check → mypy → pytest (Python 3.10,
3.11, 3.12). Coverage must stay above 80%.
