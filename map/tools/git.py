"""Async git helpers: diff, commit, and PR creation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class GitResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


async def _run(args: list[str], cwd: str | None = None) -> GitResult:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return GitResult(
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        returncode=proc.returncode if proc.returncode is not None else 1,
    )


class GitRepo:
    """Thin async wrapper around git CLI operations."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def diff(self, staged: bool = False) -> str:
        """Return the current diff (unstaged by default, staged if requested)."""
        args = ["git", "diff"]
        if staged:
            args.append("--staged")
        result = await _run(args, cwd=self.path)
        return result.stdout

    async def status(self) -> str:
        """Return `git status --short` output."""
        result = await _run(["git", "status", "--short"], cwd=self.path)
        return result.stdout

    async def add(self, paths: list[str] | None = None) -> GitResult:
        """Stage files. Stages all tracked+untracked changes if paths is None."""
        args = ["git", "add"] + (paths if paths else ["-A"])
        return await _run(args, cwd=self.path)

    async def commit(self, message: str) -> GitResult:
        """Create a commit with the given message."""
        return await _run(["git", "commit", "-m", message], cwd=self.path)

    async def current_branch(self) -> str:
        """Return the name of the currently checked-out branch."""
        result = await _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.path)
        return result.stdout.strip()

    async def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
    ) -> GitResult:
        """Open a GitHub PR using the `gh` CLI."""
        return await _run(
            ["gh", "pr", "create", "--title", title, "--body", body, "--base", base],
            cwd=self.path,
        )

    async def log(self, n: int = 10) -> str:
        """Return the last n commit log lines (one-line format)."""
        result = await _run(
            ["git", "log", f"-{n}", "--oneline"],
            cwd=self.path,
        )
        return result.stdout
