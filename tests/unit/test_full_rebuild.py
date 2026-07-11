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


@pytest.mark.parametrize("payload", ["{}", '{"generation": "../escape"}', '{"generation": "unsafe"}'])
def test_invalid_pointer_shapes_are_rejected_without_fallback(tmp_path, payload):
    workspace = tmp_path / ".fcode"
    workspace.mkdir()
    (workspace / "active.json").write_text(payload, encoding="utf-8")
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


def test_stale_managed_marker_is_removed_without_touching_active_or_unknown_files(tmp_path):
    workspace = tmp_path / ".fcode"
    generations = workspace / "generations"
    staging = workspace / "staging"
    active = generations / "generation-active"
    stale = generations / "generation-stale"
    active.mkdir(parents=True)
    stale.mkdir()
    staging.mkdir()
    (workspace / "active.json").write_text(
        json.dumps({"generation": "generation-active"}), encoding="utf-8"
    )
    (staging / "generation-stale.json").write_text(
        json.dumps({"generation": "generation-stale"}), encoding="utf-8"
    )
    unknown = staging / "keep-me.txt"
    unknown.write_text("user file", encoding="utf-8")
    FullRebuildCoordinator(str(tmp_path))._cleanup_stale_staging()
    assert active.is_dir()
    assert not stale.exists()
    assert unknown.exists()
