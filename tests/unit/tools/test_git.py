"""Unit tests for async git helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from map.tools.git import GitRepo, GitResult


def make_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.returncode = returncode
    return proc


def patch_exec(proc: MagicMock) -> object:
    return patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc))


class TestGitResult:
    def test_success_on_zero_returncode(self) -> None:
        assert GitResult(stdout="", stderr="", returncode=0).success

    def test_failure_on_nonzero_returncode(self) -> None:
        assert not GitResult(stdout="", stderr="err", returncode=1).success


class TestGitRepo:
    async def test_diff_unstaged(self) -> None:
        proc = make_proc(stdout="diff output")
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            result = await repo.diff()

        assert result == "diff output"
        args = mock_exec.call_args[0]
        assert "git" in args and "diff" in args
        assert "--staged" not in args

    async def test_diff_staged(self) -> None:
        proc = make_proc(stdout="staged diff")
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            result = await repo.diff(staged=True)

        assert result == "staged diff"
        args = mock_exec.call_args[0]
        assert "--staged" in args

    async def test_status(self) -> None:
        proc = make_proc(stdout="M  file.py\n")
        with patch_exec(proc):
            repo = GitRepo("/repo")
            result = await repo.status()

        assert "file.py" in result

    async def test_add_all(self) -> None:
        proc = make_proc()
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            await repo.add()

        args = mock_exec.call_args[0]
        assert "-A" in args

    async def test_add_specific_paths(self) -> None:
        proc = make_proc()
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            await repo.add(["src/main.py", "tests/test_main.py"])

        args = mock_exec.call_args[0]
        assert "src/main.py" in args
        assert "tests/test_main.py" in args

    async def test_commit(self) -> None:
        proc = make_proc(stdout="[main abc1234] my commit")
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            result = await repo.commit("my commit")

        assert result.success
        args = mock_exec.call_args[0]
        assert "commit" in args
        assert "my commit" in args

    async def test_current_branch(self) -> None:
        proc = make_proc(stdout="feature/my-branch\n")
        with patch_exec(proc):
            repo = GitRepo("/repo")
            branch = await repo.current_branch()

        assert branch == "feature/my-branch"

    async def test_create_pr(self) -> None:
        proc = make_proc(stdout="https://github.com/org/repo/pull/42\n")
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            result = await repo.create_pr("My PR", "body text")

        assert result.success
        args = mock_exec.call_args[0]
        assert "gh" in args
        assert "pr" in args
        assert "create" in args
        assert "My PR" in args
        assert "body text" in args

    async def test_log(self) -> None:
        proc = make_proc(stdout="abc1234 initial commit\n")
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/repo")
            output = await repo.log(n=5)

        assert "initial commit" in output
        args = mock_exec.call_args[0]
        assert "-5" in args

    async def test_cwd_passed_to_subprocess(self) -> None:
        proc = make_proc()
        with patch_exec(proc) as mock_exec:
            repo = GitRepo("/my/repo/path")
            await repo.status()

        kwargs = mock_exec.call_args[1]
        assert kwargs["cwd"] == "/my/repo/path"
