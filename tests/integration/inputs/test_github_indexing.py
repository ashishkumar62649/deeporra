"""Integration test: prepare a local git repo through GitHub-like path, then scan."""

import tempfile
from pathlib import Path
from unittest.mock import patch, ANY

from fcode.contracts import FCodeConfig, RepoInput
from fcode.inputs import RepositoryInputService
from fcode.scanner.file_scanner import scan


class FakeCP:
    returncode = 0
    stdout = ""
    stderr = ""


def test_git_prepare_then_scan():
    results = [FakeCP() for _ in range(3)]
    results[0].stdout = "git version 2.42.0\n"  # _ensure_git_available
    results[1].stdout = ""  # clone
    results[2].stdout = "abc123def456abc123def456abc123def456abc1\n"  # rev-parse

    with patch("subprocess.run", side_effect=results):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            service = RepositoryInputService()
            prepared = service.prepare(
                "https://github.com/owner/repo",
                workspace_root=ws,
            )

            repo_input = RepoInput(repo_path=str(prepared.repository_root))
            config = FCodeConfig(repo_path=str(prepared.repository_root))
            result = scan(repo_input, config)

            assert result.files == []
            assert prepared.owns_workspace is True
            assert prepared.resolved_commit == "abc123def456abc123def456abc123def456abc1"

            prepared.cleanup()
            assert not ws.exists()
