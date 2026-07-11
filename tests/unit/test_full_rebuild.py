"""Focused workspace safety checks for the full-rebuild coordinator."""

import json

import pytest

from fcode.indexing.full_rebuild import FullRebuildCoordinator, FullRebuildError


def test_malformed_active_pointer_is_not_silently_accepted(tmp_path):
    workspace = tmp_path / ".fcode"
    workspace.mkdir()
    (workspace / "active.json").write_text("not json", encoding="utf-8")
    with pytest.raises(FullRebuildError):
        FullRebuildCoordinator(str(tmp_path)).active_generation()


def test_missing_active_generation_is_not_silently_accepted(tmp_path):
    workspace = tmp_path / ".fcode"
    workspace.mkdir()
    (workspace / "active.json").write_text(
        json.dumps({"generation": "generation-missing"}), encoding="utf-8"
    )
    with pytest.raises(FullRebuildError):
        FullRebuildCoordinator(str(tmp_path)).active_generation()


def test_guard_rejects_second_writer_and_releases(tmp_path):
    coordinator = FullRebuildCoordinator(str(tmp_path))
    coordinator.workspace.mkdir()
    coordinator._acquire_guard()
    try:
        with pytest.raises(FullRebuildError):
            FullRebuildCoordinator(str(tmp_path))._acquire_guard()
    finally:
        coordinator._release_guard()
    FullRebuildCoordinator(str(tmp_path))._acquire_guard()
    FullRebuildCoordinator(str(tmp_path))._release_guard()
