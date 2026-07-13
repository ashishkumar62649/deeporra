"""Tests for RepositoryInputService entry point."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fcode.inputs import RepositoryInputService
from fcode.inputs.errors import (
    InvalidRepositorySourceError,
    RepositorySourceNotFoundError,
    UnsupportedRepositoryUrlError,
)
from fcode.inputs.models import InputKind

SERVICE = RepositoryInputService()


def test_local_folder_via_service():
    with tempfile.TemporaryDirectory() as tmp:
        result = SERVICE.prepare(tmp)
        assert result.input_kind == InputKind.LOCAL
        assert result.owns_workspace is False


def test_zip_via_service():
    import zipfile
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("project/main.py", "print('hi')")
        result = SERVICE.prepare(zip_path)
        assert result.input_kind == InputKind.ZIP
        assert result.owns_workspace is True
        result.cleanup()


def test_github_via_service():
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    results = [FakeResult(), FakeResult(), FakeResult()]
    results[0].stdout = "git version 2.42.0\n"

    with patch("subprocess.run", side_effect=results):
        result = SERVICE.prepare(
            "https://github.com/owner/repo",
            workspace_root=Path(tempfile.mkdtemp()),
        )
        assert result.input_kind == InputKind.GITHUB
        assert result.owns_workspace is True
        result.cleanup()


def test_nonexistent_path_rejected():
    with pytest.raises(RepositorySourceNotFoundError):
        SERVICE.prepare("/nonexistent/path/xyz789")


def test_unsupported_url_rejected():
    with pytest.raises(UnsupportedRepositoryUrlError):
        SERVICE.prepare("https://gitlab.com/owner/repo")


def test_empty_source_rejected():
    with pytest.raises(InvalidRepositorySourceError):
        SERVICE.prepare("")


def test_path_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        result = SERVICE.prepare(Path(tmp))
        assert result.input_kind == InputKind.LOCAL


def test_ref_passed_to_github():
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""
    results = [
        FakeResult(),  # _ensure_git_available: git --version
        FakeResult(),  # clone
        FakeResult(),  # rev-parse
    ]
    results[0].stdout = "git version 2.42.0\n"
    results[2].stdout = "abc123\n"

    with patch("subprocess.run", side_effect=results):
        result = SERVICE.prepare(
            "https://github.com/owner/repo",
            ref="main",
            workspace_root=Path(tempfile.mkdtemp()),
        )
        assert result.resolved_commit == "abc123"
        result.cleanup()
