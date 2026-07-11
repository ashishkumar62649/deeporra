"""WP5 Step 5 real staged-rebuild replacement coverage."""

import socket
import sys
import types
from pathlib import Path

from fcode.chunking import Chunker
from fcode.contracts import FCodeConfig, IndexPhase, IndexState
from fcode.embeddings import EmbeddingEncoder, EXPECTED_DIMENSION
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.indexing.full_rebuild import FullRebuildCoordinator
from fcode.parser.python_ast import parse
from fcode.scanner.file_scanner import scan
from fcode.storage.chroma_store import ChromaStore
from fcode.storage.fts_store import FTSStore
from fcode.storage.graph_store import GraphStore
from fcode.storage.sqlite_store import SQLiteStore


class _FakeSentenceTransformer:
    calls = []

    def __init__(self, model_name, *, device, local_files_only):
        self.calls.append((model_name, device, local_files_only))

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **_):
        return [[0.25] * EXPECTED_DIMENSION for _ in texts]


class _Scanner:
    def scan(self, repo, config):
        return scan(repo, config)


class _Parser:
    def parse(self, file):
        return parse(file)


class _GraphBuilder:
    def build(self, parsed_files):
        return build_graph(parsed_files)


def _service():
    return IndexService(
        _Scanner(), _Parser(), Chunker(), encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder()
    )


def _write_a(repo: Path):
    (repo / "app.py").write_text(
        "from os import path\n\n"
        "class LegacyService:\n"
        "    def legacy_method(self):\n"
        "        return 'alpha-only-token'\n\n"
        "@app.get('/alpha')\n"
        "def alpha_handler():\n"
        "    return LegacyService().legacy_method()\n\n"
        "API_TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'\n",
        encoding="utf-8",
    )
    (repo / "test_app.py").write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
    (repo / "README.md").write_text("# Alpha Manual\n\nalpha-only-token\n", encoding="utf-8")
    (repo / "guide.rst").write_text("Alpha\n=====\n\nGuide\n", encoding="utf-8")
    (repo / "settings.toml").write_text("feature = 'alpha-only-token'\n" * 120, encoding="utf-8")
    (repo / "broken.py").write_text("def broken(:\n", encoding="utf-8")


def _write_b(repo: Path):
    (repo / "settings.toml").unlink()
    (repo / "guide.rst").unlink()
    (repo / "test_app.py").unlink()
    (repo / "app.py").write_text(
        "class ModernService:\n"
        "    def beta_method(self):\n"
        "        return 'beta-only-token'\n\n"
        "@app.post('/beta')\n"
        "def beta_handler():\n"
        "    return ModernService().beta_method()\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Beta Manual\n\nbeta-only-token\n", encoding="utf-8")
    (repo / "new_module.py").write_text("def beta_only_symbol():\n    return 'beta-only-token'\n", encoding="utf-8")


def _active_evidence(repo: Path):
    paths = FullRebuildCoordinator(str(repo)).active_paths()
    sqlite = SQLiteStore(str(paths.database))
    chroma = ChromaStore(str(paths.chroma))
    sqlite.connect()
    chroma.open()
    try:
        repo_id = sqlite.find_repository(str(repo.resolve()))
        fts = FTSStore(sqlite.conn)
        graph = GraphStore(sqlite.conn)
        return {
            "generation": paths.root.name,
            "repo_id": repo_id,
            "alpha": fts.search_chunks(sqlite.conn, "alpha", repo_id),
            "beta": fts.search_chunks(sqlite.conn, "beta", repo_id),
            "vectors": set((chroma.get_embeddings(repo_id).get("ids") or [])),
            "nodes": graph.get_nodes(sqlite.conn, repo_id),
            "edges": graph.get_edges(sqlite.conn, repo_id),
            "status": sqlite.read_index_status(repo_id),
        }
    finally:
        chroma.close()
        sqlite.close()


def test_wp5_full_rebuild_replaces_only_after_staged_verification(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    attempts = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: attempts.append((a, k)))

    _FakeSentenceTransformer.calls.clear()
    first = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert first.run_result.state == IndexState.COMPLETE
    assert first.run_result.phase == IndexPhase.PERSIST
    assert first.completed_phase == IndexPhase.PERSIST
    assert first.state_history[-2:] == (IndexState.STORING, IndexState.COMPLETE)
    a = _active_evidence(repo)
    assert a["status"]["status"] == "complete"
    assert a["alpha"] and a["vectors"] and a["nodes"] and a["edges"]
    assert all(len(record.vector) == EXPECTED_DIMENSION for record in first.embedding_result.records)
    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in str(a)

    _write_b(repo)
    original_upsert = ChromaStore.upsert_embeddings

    def fail_after_write(self, repo_id, records):
        original_upsert(self, repo_id, records)
        raise RuntimeError("controlled vector failure")

    monkeypatch.setattr(ChromaStore, "upsert_embeddings", fail_after_write)
    failed = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert failed.run_result.state == IndexState.ERROR
    after_failed = _active_evidence(repo)
    assert after_failed["generation"] == a["generation"]
    assert after_failed["vectors"] == a["vectors"]
    assert after_failed["alpha"] and not after_failed["beta"]

    monkeypatch.setattr(ChromaStore, "upsert_embeddings", original_upsert)
    success = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert success.run_result.state == IndexState.COMPLETE
    b = _active_evidence(repo)
    assert b["generation"] != a["generation"]
    assert b["beta"] and not b["alpha"]
    assert b["vectors"] == {record.chunk_id for record in success.embedding_result.records}
    assert all(edge["source_node_id"] in {node["node_id"] for node in b["nodes"]} for edge in b["edges"])
    assert all(edge["target_node_id"] in {node["node_id"] for node in b["nodes"]} for edge in b["edges"])
    assert _FakeSentenceTransformer.calls == [
        ("sentence-transformers/all-MiniLM-L6-v2", "cpu", True)
    ] * 3
    assert attempts == []
