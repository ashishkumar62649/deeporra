"""Tests for ZIP archive preparation."""

import os
import tempfile
from pathlib import Path
import zipfile

import pytest

from fcode.inputs.errors import (
    ArchiveLimitExceededError,
    UnsafeArchiveError,
)
from fcode.inputs.models import InputKind
from fcode.inputs.zip_preparation import prepare_zip
from fcode.inputs.workspace import OwnedWorkspace


def _make_zip(zip_path, entries):
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        for entry in entries:
            if isinstance(entry, tuple):
                name, content = entry
                zf.writestr(name, content)
            else:
                zf.writestr(entry, "")


def _workspace():
    return OwnedWorkspace(Path(tempfile.mkdtemp()))


def test_normal_single_root_zip():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        _make_zip(zip_path, [
            ("project/", ""),
            ("project/src/main.py", "print('hello')"),
            ("project/pyproject.toml", "[project]\nname = 'test'\n"),
        ])
        ws = _workspace()
        result = prepare_zip(zip_path, ws.root)
        assert result.input_kind == InputKind.ZIP
        assert result.repository_root.name == "project"
        assert (result.repository_root / "src" / "main.py").exists()
        assert result.owns_workspace is True


def test_normal_multi_root_zip():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        _make_zip(zip_path, [
            ("src/main.py", "print('hello')"),
            ("pyproject.toml", "[project]\n"),
        ])
        ws = _workspace()
        result = prepare_zip(zip_path, ws.root)
        assert result.repository_root == ws.root


def test_empty_zip():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "empty.zip")
        _make_zip(zip_path, [])
        ws = _workspace()
        result = prepare_zip(zip_path, ws.root)
        assert result.repository_root.is_dir()
        assert result.repository_root == ws.root


def test_nested_files_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        _make_zip(zip_path, [
            ("repo/a/b/c/deep.py", "x=1"),
        ])
        ws = _workspace()
        result = prepare_zip(zip_path, ws.root)
        assert (result.repository_root / "a" / "b" / "c" / "deep.py").exists()


def test_path_traversal_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        _make_zip(zip_path, [
            ("../../escape.txt", "bad"),
        ])
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)


def test_absolute_path_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        _make_zip(zip_path, [
            ("/etc/passwd", "root:x"),
        ])
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)


def test_windows_drive_path_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        _make_zip(zip_path, [
            ("C:\\windows\\system32\\evil.exe", "bad"),
        ])
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)


def test_duplicate_normalized_destination_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("a/./x.py", "one")
            zf.writestr("a/x.py", "two")
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)


def test_unsafe_symlink_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            info = zipfile.ZipInfo("link.txt")
            info.external_attr = 0o120000 << 16
            zf.writestr(info, "/etc/passwd")
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)


def test_file_count_limit_enforced():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "big.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            for i in range(10001):
                zf.writestr(f"file_{i}.py", "x=1\n")
        ws = _workspace()
        with pytest.raises(ArchiveLimitExceededError):
            prepare_zip(zip_path, ws.root)


def test_individual_file_limit_enforced():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bigfile.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("huge.bin", "x" * 200_000_000)
        ws = _workspace()
        with pytest.raises(ArchiveLimitExceededError):
            prepare_zip(zip_path, ws.root)


def test_total_size_limit_enforced():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "manyfiles.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            for i in range(200):
                zf.writestr(f"file_{i}.bin", "x" * 3_000_000)
        ws = _workspace()
        with pytest.raises(ArchiveLimitExceededError):
            prepare_zip(zip_path, ws.root)


def test_partial_extraction_cleaned_after_failure():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "bad.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("safe.py", "ok")
            info = zipfile.ZipInfo("../../escape.py")
            zf.writestr(info, "bad")
        ws = _workspace()
        with pytest.raises(UnsafeArchiveError):
            prepare_zip(zip_path, ws.root)
        assert not ws.root.exists()


def test_owned_workspace_cleanup_works():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        _make_zip(zip_path, [("project/main.py", "x=1")])
        ws = _workspace()
        result = prepare_zip(zip_path, ws.root)
        root = result.repository_root
        assert root.exists()
        result.cleanup()
        assert not root.exists()


def test_original_zip_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        _make_zip(zip_path, [("main.py", "x=1")])
        original_bytes = open(zip_path, "rb").read()
        ws = _workspace()
        prepare_zip(zip_path, ws.root)
        assert open(zip_path, "rb").read() == original_bytes
