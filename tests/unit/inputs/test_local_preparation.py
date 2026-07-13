"""Tests for local folder preparation."""

import os
import tempfile

import pytest

from fcode.inputs import PreparedRepository
from fcode.inputs.local_preparation import prepare_local
from fcode.inputs.errors import (
    InvalidRepositorySourceError,
    RepositorySourceNotFoundError,
)
from fcode.inputs.models import InputKind


def test_existing_normal_directory_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert result.input_kind == InputKind.LOCAL
        assert result.repository_root.is_dir()
        assert result.owns_workspace is False


def test_non_git_directory_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert result.owns_workspace is False


def test_nonexistent_path_rejected():
    path = os.path.join(tempfile.gettempdir(), "nonexistent_dir_xyz123")
    with pytest.raises(RepositorySourceNotFoundError):
        prepare_local(path)


def test_local_folder_not_copied():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert str(result.repository_root) == os.path.realpath(tmp)


def test_local_folder_not_modified():
    with tempfile.TemporaryDirectory() as tmp:
        test_file = os.path.join(tmp, "test.txt")
        with open(test_file, "w") as f:
            f.write("original")
        result = prepare_local(tmp)
        with open(os.path.join(result.repository_root, "test.txt")) as f:
            assert f.read() == "original"


def test_cleanup_does_not_delete_local_folder():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert result.cleanup is None
        assert os.path.isdir(tmp)


def test_empty_directory_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert result.repository_root.is_dir()


def test_unicode_and_spaces_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "my repo (测试)")
        os.makedirs(path)
        result = prepare_local(path)
        assert result.display_name == "my repo (测试)"
        assert result.repository_root.is_dir()


def test_regular_file_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "file.txt")
        with open(path, "w") as f:
            f.write("not a dir")
        with pytest.raises(InvalidRepositorySourceError):
            prepare_local(path)


def test_returns_prepared_repository_type():
    with tempfile.TemporaryDirectory() as tmp:
        result = prepare_local(tmp)
        assert isinstance(result, PreparedRepository)
