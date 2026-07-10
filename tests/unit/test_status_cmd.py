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

    def test_set_service_does_not_affect_placeholder(self):
        fake = FakeStatusService()
        set_status_service(fake)
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 1
        assert "Status command implementation has not started." in result.stdout


class TestPlaceholder:
    def test_placeholder_unchanged(self):
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 1
        assert "Status command implementation has not started." in result.stdout

    def test_placeholder_with_explicit_path(self):
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "status", "."],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 1
        assert "Status command implementation has not started." in result.stdout
