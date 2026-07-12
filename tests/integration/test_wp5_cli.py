"""Typer-level index/status activation using the real production factory."""

import sys
import types
import json
from dataclasses import fields

from typer.testing import CliRunner

from fcode.cli.main import app
from fcode.embeddings import EXPECTED_DIMENSION
from fcode.storage.chroma_store import ChromaStore
from fcode.storage.sqlite_store import SQLiteStore
from fcode.cli.dependencies import create_index_service
from fcode.contracts import FCodeConfig


class _FakeSentenceTransformer:
    calls = []
    def __init__(self, model_name, *, device, local_files_only):
        self.calls.append((model_name, device, local_files_only))
    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION
    def encode(self, texts, **_):
        return [[0.1] * EXPECTED_DIMENSION for _ in texts]


def _write(repo, term):
    (repo / "app.py").write_text(
        f"@app.get('/{term}')\ndef {term}_handler():\n    return '{term}'\n\n"
        "API_TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text(f"# {term}\n", encoding="utf-8")


def test_cli_activates_full_index_and_active_status(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "alpha")
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    runner = CliRunner()
    _FakeSentenceTransformer.calls.clear()

    before = runner.invoke(app, ["status", str(repo)])
    assert before.exit_code == 0 and "No active index." in before.output
    assert not (repo / ".fcode").exists()

    first = runner.invoke(app, ["index", str(repo)])
    assert first.exit_code == 0 and "Index complete." in first.output
    assert "ghp_" not in first.output
    after = runner.invoke(app, ["status", str(repo)])
    assert after.exit_code == 0 and "state=complete" in after.output
    assert "chunks=" in after.output

    _write(repo, "beta")
    original_upsert = ChromaStore.upsert_embeddings
    with monkeypatch.context() as patch:
        patch.setattr(ChromaStore, "upsert_embeddings", lambda self, *a: (_ for _ in ()).throw(RuntimeError("private failure")))
        failed = runner.invoke(app, ["index", str(repo)])
    assert failed.exit_code == 1 and "Index failed." in failed.output
    preserved = runner.invoke(app, ["status", str(repo)])
    assert preserved.exit_code == 0 and "state=complete" in preserved.output

    final = runner.invoke(app, ["index", str(repo)])
    assert final.exit_code == 0 and "Index complete." in final.output
    assert _FakeSentenceTransformer.calls == [
        ("sentence-transformers/all-MiniLM-L6-v2", "cpu", True)
    ] * 3


def test_status_rejects_invalid_active_pointer_without_leaking_workspace_details(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    workspace = repo / ".fcode"
    workspace.mkdir()
    runner = CliRunner()
    for payload in ("not json", "{}", json.dumps({"generation": "../escape"}), json.dumps({"generation": "generation-missing"})):
        (workspace / "active.json").write_text(payload, encoding="utf-8")
        result = runner.invoke(app, ["status", str(repo)])
        assert result.exit_code == 1
        assert result.output == "Status unavailable.\n"
        assert str(repo) not in result.output
        assert payload not in result.output


def test_status_resolves_active_pointer_once_for_one_snapshot(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "alpha")
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0
    from fcode.indexing.full_rebuild import FullRebuildCoordinator
    original = FullRebuildCoordinator.active_generation
    calls = {"count": 0}
    def counted(self):
        calls["count"] += 1
        return original(self)
    monkeypatch.setattr(FullRebuildCoordinator, "active_generation", counted)
    result = runner.invoke(app, ["status", str(repo)])
    assert result.exit_code == 0
    assert calls["count"] == 1


def test_active_status_counts_match_completed_run_and_cli(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "alpha")
    (repo / "good.py").write_text("def useful():\n    return 1\n", encoding="utf-8")
    (repo / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    config = FCodeConfig(repo_path=str(repo))
    run_counts = create_index_service(config).run_index(config).counts
    service = create_index_service(config, for_status=True)
    assert service.get_status().counts == run_counts
    assert service.get_counts() == run_counts
    output = CliRunner().invoke(app, ["status", str(repo)])
    assert output.exit_code == 0
    rendered = dict(part.split("=", 1) for part in output.output.splitlines()[1].split())
    assert {field.name: int(rendered[field.name]) for field in fields(run_counts)} == {
        field.name: getattr(run_counts, field.name) for field in fields(run_counts)
    }
    assert run_counts.parsed < run_counts.scanned
    assert run_counts.parse_errors == 1
    assert run_counts.embedding_skipped >= 1
    generation = json.loads((repo / ".fcode" / "active.json").read_text(encoding="utf-8"))["generation"]
    store = SQLiteStore(str(repo / ".fcode" / "generations" / generation / "index.db"))
    store.connect()
    try:
        statuses = {row["path"]: row["parse_status"] for row in store.conn.execute("SELECT path, parse_status FROM files")}
    finally:
        store.close()
    assert statuses["good.py"] == "parsed"
    assert statuses["broken.py"] == "error"
    assert statuses["README.md"] == "not_applicable"
