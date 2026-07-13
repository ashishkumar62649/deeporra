"""Tests for GitHub preparation with mocked subprocess."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from fcode.inputs.errors import (
    GitCloneError,
    GitUnavailableError,
    UnsupportedRepositoryUrlError,
)
from fcode.inputs.github_preparation import (
    _clone,
    _ensure_git_available,
    _rev_parse_head,
    _run_git,
    prepare_github,
)
from fcode.inputs.models import InputKind


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_git_unavailable_raises_typed_error():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(GitUnavailableError):
            _ensure_git_available()


def test_subprocess_uses_argument_list():
    with patch("subprocess.run", return_value=FakeCompletedProcess()) as mock:
        _ensure_git_available()
        args = mock.call_args[0][0]
        assert isinstance(args, list)
        assert args[0] == "git"
        assert "--version" in args


def test_run_git_uses_no_shell():
    with patch("subprocess.run", return_value=FakeCompletedProcess()) as mock:
        _run_git(["rev-parse", "HEAD"], cwd=Path(tempfile.mkdtemp()))
        assert mock.call_args[1].get("shell") is None or mock.call_args[1].get("shell") is False


def test_branch_clone_command_correct():
    with patch("subprocess.run", return_value=FakeCompletedProcess(stdout="abc123\n")):
        _ensure_git_available()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            _clone("https://github.com/o/r.git", target, ref="main")
            args, kwargs = subprocess.run.call_args
            cmd = args[0]
            assert "--depth" in cmd
            assert "--branch" in cmd
            assert "main" in cmd
            assert "core.hooksPath=/dev/null" in cmd


def test_commit_checkout_behavior():
    results = [
        FakeCompletedProcess(stdout="git version 2.42.0\n"),  # _ensure_git_available
        FakeCompletedProcess(stdout=""),  # clone
        FakeCompletedProcess(stdout="abc123def456\n"),  # checkout
        FakeCompletedProcess(stdout="abc123def456abc123def456abc123def456abc1\n"),  # rev-parse
    ]
    with patch("subprocess.run", side_effect=results):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repo"
            _clone("https://github.com/o/r.git", target, ref="abc123def456abc123def456abc123def456abc1")
            calls = [call for call in subprocess.run.call_args_list if "version" not in call.args[0]]
            assert len(calls) >= 2
            assert "checkout" in calls[1].args[0]


def test_resolved_commit_recorded():
    results = [
        FakeCompletedProcess(stdout="git version 2.42.0\n"),  # _ensure_git_available
        FakeCompletedProcess(stdout=""),  # clone
        FakeCompletedProcess(stdout="abc123def456abc123def456abc123def456abc1\n"),  # rev-parse
    ]
    with patch("subprocess.run", side_effect=results):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            result = prepare_github(
                "https://github.com/owner/repo.git",
                workspace_root=ws,
            )
            assert result.input_kind == InputKind.GITHUB
            assert result.resolved_commit == "abc123def456abc123def456abc123def456abc1"


def test_clone_failure_cleans_workspace():
    with patch("subprocess.run", return_value=FakeCompletedProcess(stdout="git version 2.42.0\n")) as mock:
        mock.side_effect = [
            FakeCompletedProcess(stdout="git version 2.42.0\n"),  # _ensure_git_available
            GitCloneError("clone failed"),  # clone
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            with pytest.raises(GitCloneError):
                prepare_github("https://github.com/owner/repo.git", workspace_root=ws)
            assert not ws.exists()


def test_credentials_not_leaked():
    with patch("subprocess.run", side_effect=[
        FakeCompletedProcess(stdout="git version 2.42.0\n"),  # _ensure_git_available
        FakeCompletedProcess(returncode=1, stderr="fatal: Authentication failed for https://user:password@github.com/owner/repo.git"),
    ]):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            with pytest.raises(GitCloneError) as exc:
                prepare_github("https://github.com/owner/repo.git", workspace_root=ws)
            msg = str(exc.value)
            assert "password" not in msg.lower()
            assert "user:" not in msg.lower()
            assert "token" not in msg.lower()


def test_cleanup_removes_only_owned_clone():
    results = [
        FakeCompletedProcess(stdout="git version 2.42.0\n"),  # _ensure_git_available
        FakeCompletedProcess(stdout=""),  # clone
        FakeCompletedProcess(stdout="abc\n"),  # rev-parse
    ]
    with patch("subprocess.run", side_effect=results):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            result = prepare_github("https://github.com/owner/repo.git", workspace_root=ws)
            repo_root = result.repository_root
            assert repo_root.exists()
            result.cleanup()
            assert not repo_root.exists()


def test_unsupported_host_rejected():
    with patch("subprocess.run", return_value=FakeCompletedProcess(stdout="git version 2.42.0\n")):
        with pytest.raises(UnsupportedRepositoryUrlError):
            prepare_github("https://gitlab.com/owner/repo.git", workspace_root=Path(tempfile.mkdtemp()))


def test_tests_do_not_contact_network():
    with patch("subprocess.run") as mock:
        mock.side_effect = FileNotFoundError
        with pytest.raises(GitUnavailableError):
            prepare_github("https://github.com/owner/repo.git", workspace_root=Path(tempfile.mkdtemp()))
