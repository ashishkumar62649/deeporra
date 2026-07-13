"""Tests for workspace lifecycle management."""

import os
import tempfile
from pathlib import Path

import pytest

from fcode.inputs.errors import WorkspaceCleanupError
from fcode.inputs.workspace import OwnedWorkspace


def test_auto_temp_directory():
    ws = OwnedWorkspace()
    assert ws.root.exists()
    assert ws.root.is_dir()
    assert ws.root.name.startswith("fcode_")
    ws.cleanup()


def test_explicit_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "workspace"
        ws = OwnedWorkspace(root)
        assert ws.root == root
        assert root.exists()
        ws.cleanup()
        assert not root.exists()


def test_cleanup_is_idempotent():
    ws = OwnedWorkspace()
    ws.cleanup()
    ws.cleanup()


def test_context_manager_cleanup():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ctx"
        with OwnedWorkspace(root) as ws:
            assert ws.root.exists()
        assert not root.exists()


def test_context_manager_cleanup_on_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ctx_err"
        try:
            with OwnedWorkspace(root) as ws:
                assert ws.root.exists()
                raise ValueError("test error")
        except ValueError:
            pass
        assert not root.exists()


def test_refuses_to_clean_drive_root():
    root = Path("/") if os.name != "nt" else Path("C:\\")
    ws = OwnedWorkspace(Path(tempfile.mkdtemp()))
    with pytest.raises(WorkspaceCleanupError):
        ws._validate_cleanup_safety(root)


def test_refuses_to_clean_fcode_project():
    ws = OwnedWorkspace(Path(tempfile.mkdtemp()))
    with pytest.raises(WorkspaceCleanupError):
        ws._validate_cleanup_safety(Path(os.getcwd()))


def test_cleanup_does_not_touch_unrelated_paths():
    with tempfile.TemporaryDirectory() as tmp:
        unrelated = Path(tmp) / "unrelated"
        unrelated.mkdir()
        unrelated_file = unrelated / "keep.txt"
        unrelated_file.write_text("important")
        ws_root = Path(tmp) / "workspace"
        ws = OwnedWorkspace(ws_root)
        ws.cleanup()
        assert unrelated_file.exists()
        assert unrelated.exists()
