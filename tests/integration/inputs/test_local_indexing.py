"""Integration test: prepare a local folder, then scan it with the existing scanner."""

import os
import tempfile
from pathlib import Path

from fcode.contracts import FCodeConfig, RepoInput
from fcode.inputs import RepositoryInputService
from fcode.scanner.file_scanner import scan


def test_local_folder_prepare_then_scan():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "myproject"
        repo_dir.mkdir()
        (repo_dir / "main.py").write_text("print('hello')\n")
        (repo_dir / "utils.py").write_text("def helper():\n    pass\n")

        service = RepositoryInputService()
        prepared = service.prepare(str(repo_dir))

        repo_input = RepoInput(repo_path=str(prepared.repository_root))
        config = FCodeConfig(repo_path=str(prepared.repository_root))
        result = scan(repo_input, config)

        assert len(result.files) == 2
        paths = {f.file_path for f in result.files}
        assert "main.py" in paths
        assert "utils.py" in paths
        assert prepared.owns_workspace is False


def test_local_folder_content_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "myproject"
        repo_dir.mkdir()
        test_file = repo_dir / "data.txt"
        test_file.write_text("original content\n")

        original_bytes = test_file.read_bytes()
        service = RepositoryInputService()
        prepared = service.prepare(str(repo_dir))

        assert prepared.repository_root == repo_dir.resolve()
        assert test_file.read_bytes() == original_bytes
