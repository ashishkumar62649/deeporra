"""Subprocess-level CLI tests — verify real execution and numeric exit codes."""

import os
import subprocess
import sys
import shutil
from pathlib import Path

import pytest


def _invoke(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run python -m deeporra <args> and capture stdout, stderr, return code."""
    return subprocess.run(
        [sys.executable, "-m", "deeporra", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _DEEPORRA_on_path() -> bool:
    """Check if deeporra console script exists in the active project venv."""
    scripts_dir = Path(sys.executable).parent
    return (scripts_dir / "deeporra.exe").exists() or (scripts_dir / "deeporra").exists()


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

    def test_index_no_DEEPORRA_dir_created(self, tmp_path):
        DEEPORRA_dir = os.path.join(os.getcwd(), ".deeporra")
        existed_before = os.path.isdir(DEEPORRA_dir)
        _invoke("index", str(tmp_path / "nonexistent"))
        assert os.path.isdir(DEEPORRA_dir) == existed_before


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
    def test_dashboard_not_deferred(self):
        result = _invoke("dashboard", "--help")
        assert result.returncode == 0
        assert "Start Streamlit dashboard" in result.stdout

    def test_dashboard_help_shows_port(self):
        result = _invoke("dashboard", "--help")
        assert result.returncode == 0
        assert "--port" in result.stdout


class TestMCP:
    def test_mcp_help(self):
        result = _invoke("mcp", "--help")
        assert result.returncode == 0
        assert "Start MCP stdio server" in result.stdout

    def test_mcp_not_deferred(self):
        result = _invoke("mcp", "--help")
        assert "This command is not available" not in result.stdout


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
    """Test that `deeporra --help` works when the console script exists in the project venv."""

    def test_deeporra_command_works(self):
        import sysconfig
        import importlib.metadata as md
        scripts_dir = Path(sysconfig.get_path("scripts"))
        deeporra_exe = scripts_dir / "deeporra.exe"
        if not deeporra_exe.exists():
            deeporra_exe = scripts_dir / "deeporra"
        assert deeporra_exe.exists(), (
            f"deeporra console script not found in {scripts_dir}\n"
            f"  sys.executable: {sys.executable}\n"
            f"  sys.prefix:     {sys.prefix}\n"
            f"  entry points:   {[ep for ep in md.entry_points(group='console_scripts') if ep.name == 'deeporra']}\n"
            f"  shutil.which:   {shutil.which('deeporra')}"
        )
        result = subprocess.run(
            [str(deeporra_exe), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        for cmd in ("index", "status", "doctor", "dashboard", "mcp", "setup"):
            assert cmd in result.stdout
