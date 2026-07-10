"""Service composition tests for the index command."""

import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from fcode.contracts import FCodeConfig, IndexRunResult, IndexState, IndexPhase
from fcode.cli.commands.index_cmd import (
    get_index_service,
    set_index_service,
)


class FakeIndexService:
    def __init__(self):
        self.called = False
        self.last_config = None

    def run_index(self, config: FCodeConfig) -> IndexRunResult:
        self.called = True
        self.last_config = config
        return IndexRunResult(state=IndexState.PASSED, phase=IndexPhase.PERSIST)

    def get_status(self):
        return None

    def get_counts(self):
        return None


class TestComposition:
    def test_no_service_returns_none(self):
        assert get_index_service() is None

    def test_set_service_in_process(self):
        fake = FakeIndexService()
        set_index_service(fake)
        assert get_index_service() is fake

    def test_set_service_does_not_affect_placeholder(self):
        fake = FakeIndexService()
        set_index_service(fake)
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "index", "."],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 1
        assert "Index command implementation has not started." in result.stdout

    def test_configure_app_in_main(self):
        from fcode.cli.main import configure_app
        assert configure_app is not None


class TestPlaceholder:
    def test_placeholder_unchanged(self):
        result = subprocess.run(
            [sys.executable, "-m", "fcode", "index", "."],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 1
        assert "Index command implementation has not started." in result.stdout
