"""Integration test: prepare a ZIP, then scan it with the existing scanner."""

import tempfile
import zipfile
from pathlib import Path

from fcode.contracts import FCodeConfig, RepoInput
from fcode.inputs import RepositoryInputService
from fcode.scanner.file_scanner import scan


def test_zip_prepare_then_scan():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "repo.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("project/main.py", "print('hello')\n")
            zf.writestr("project/utils.py", "def helper():\n    pass\n")

        original_bytes = zip_path.read_bytes()
        service = RepositoryInputService()
        prepared = service.prepare(str(zip_path))

        repo_input = RepoInput(repo_path=str(prepared.repository_root))
        config = FCodeConfig(repo_path=str(prepared.repository_root))
        result = scan(repo_input, config)

        assert len(result.files) == 2
        assert prepared.owns_workspace is True
        assert zip_path.read_bytes() == original_bytes

        prepared.cleanup()
        assert not prepared.repository_root.exists()
