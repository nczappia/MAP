"""Async subprocess wrapper for the Claude Code CLI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class ClaudeCodeResult:
    stdout: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


@dataclass
class ClaudeCodeRunner:
    """Runs `claude --print` as an async subprocess.

    Args:
        executable: path or name of the claude CLI binary.
        default_tools: tool names always passed via --allowedTools.
    """

    executable: str = "claude"
    default_tools: list[str] = field(default_factory=list)

    async def run(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
        system: str | None = None,
        allowed_tools: list[str] | None = None,
        timeout: float | None = None,
    ) -> ClaudeCodeResult:
        """Spawn claude CLI and return its output.

        Args:
            prompt: the task prompt passed to claude.
            cwd: working directory for the subprocess.
            system: optional system prompt prepended to the conversation.
            allowed_tools: tool names to allow; merged with default_tools.
            timeout: seconds before the subprocess is killed (None = unlimited).
        """
        tools = list(self.default_tools)
        if allowed_tools:
            for t in allowed_tools:
                if t not in tools:
                    tools.append(t)

        cmd = [self.executable, "--print"]
        if system:
            cmd += ["--system-prompt", system]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        cmd.append(prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise

        return ClaudeCodeResult(
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            returncode=proc.returncode if proc.returncode is not None else 1,
        )
