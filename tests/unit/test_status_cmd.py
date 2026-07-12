"""Service composition tests for the status command."""

import subprocess
import sys

from fcode.cli.commands.status_cmd import (
    get_status_service,
    set_status_service,
)


class FakeStatusService:
    def __init__(self):
        self.called = False

    def get_status(self):
        self.called = True
        return None

    def doctor(self):
        return None


class TestComposition:
    def test_no_service_returns_none(self):
        assert get_status_service() is None

    def test_set_service_in_process(self):
        fake = FakeStatusService()
        set_status_service(fake)
        assert get_status_service() is fake

    def test_set_service_is_process_local(self):
        fake = FakeStatusService()
        set_status_service(fake)
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "No active index." in result.stdout


class TestCommand:
    def test_no_active_index_is_healthy(self):
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "No active index." in result.stdout

    def test_no_active_index_with_explicit_path(self):
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status", "."],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "No active index." in result.stdout
