"""Subprocess-level CLI tests — verify real execution and numeric exit codes."""

import os
import subprocess
import sys
import shutil

import pytest


def _invoke(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run python -m fcode <args> and capture stdout, stderr, return code."""
    return subprocess.run(
        [sys.executable, "-m", "fcode", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _fcode_on_path() -> bool:
    return shutil.which("fcode") is not None


class TestHelp:
    def test_help_exit_code(self):
        result = _invoke("--help")
        assert result.returncode == 0

    def test_help_contains_all_commands(self):
        result = _invoke("--help")
        assert result.returncode == 0
        for cmd in ("index", "status", "doctor", "dashboard", "mcp", "setup"):
            assert cmd in result.stdout, f"Missing command: {cmd}"

    def test_help_non_empty(self):
        result = _invoke("--help")
        assert len(result.stdout) > 50


class TestIndex:
    def test_index_placeholder_exit_code(self, tmp_path):
        result = _invoke("index", str(tmp_path / "nonexistent"))
        assert result.returncode == 1

    def test_index_failure_message_is_sanitized(self, tmp_path):
        result = _invoke("index", str(tmp_path / "nonexistent"))
        assert "Index failed." in result.stdout

    def test_index_no_fcode_dir_created(self, tmp_path):
        fcode_dir = os.path.join(os.getcwd(), ".fcode")
        existed_before = os.path.isdir(fcode_dir)
        _invoke("index", str(tmp_path / "nonexistent"))
        assert os.path.isdir(fcode_dir) == existed_before


class TestStatus:
    def test_status_no_index_exit_code(self):
        result = _invoke("status")
        assert result.returncode == 0

    def test_status_no_index_message(self):
        result = _invoke("status")
        assert "No active index." in result.stdout

    def test_status_no_index_with_explicit_path(self):
        result = _invoke("status", ".")
        assert result.returncode == 0
        assert "No active index." in result.stdout


class TestDoctor:
    def test_doctor_exit_code(self):
        """Real subprocess smoke test — verifies the doctor command starts and exits."""
        result = _invoke("doctor", timeout=30)
        assert result.returncode in (0, 1)


class TestDashboard:
    def test_dashboard_exit_code(self):
        result = _invoke("dashboard")
        assert result.returncode == 2

    def test_dashboard_deferred_message(self):
        result = _invoke("dashboard")
        assert "This command is not available" in result.stdout

    def test_dashboard_with_port(self):
        result = _invoke("dashboard", "--port", "8600")
        assert result.returncode == 2
        assert "This command is not available" in result.stdout


class TestMCP:
    def test_mcp_with_repo_exit_code(self):
        result = _invoke("mcp", "--repo", ".")
        assert result.returncode == 2

    def test_mcp_with_repo_message(self):
        result = _invoke("mcp", "--repo", ".")
        assert "This command is not available" in result.stdout

    def test_mcp_missing_repo_is_error(self):
        result = _invoke("mcp")
        assert result.returncode != 0
        assert len(result.stderr) > 0 or len(result.stdout) > 0


class TestSetup:
    def test_setup_claude(self):
        result = _invoke("setup", "claude", "--repo", ".")
        assert result.returncode == 2
        assert "This command is not available" in result.stdout

    def test_setup_codex(self):
        result = _invoke("setup", "codex", "--repo", ".")
        assert result.returncode == 2
        assert "This command is not available" in result.stdout

    def test_setup_opencode(self):
        result = _invoke("setup", "opencode", "--repo", ".")
        assert result.returncode == 2
        assert "This command is not available" in result.stdout

    def test_setup_invalid_agent(self):
        result = _invoke("setup", "invalid-agent", "--repo", ".")
        assert result.returncode == 1
        assert "Invalid agent" in result.stdout or "Invalid agent" in result.stderr

    def test_setup_missing_repo_is_error(self):
        result = _invoke("setup", "claude")
        assert result.returncode != 0
        assert len(result.stderr) > 0 or len(result.stdout) > 0


class TestConsoleScript:
    """Test that `fcode --help` works when the console script is on PATH."""

    def test_fcode_command_works(self):
        if not _fcode_on_path():
            pytest.skip("fcode not on PATH")
        result = subprocess.run(
            ["fcode", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        for cmd in ("index", "status", "doctor", "dashboard", "mcp", "setup"):
            assert cmd in result.stdout
