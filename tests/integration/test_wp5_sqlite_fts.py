"""WP5 Step 4 integration: real pipeline through SQLite metadata and FTS."""

import socket
import sys
import types
from pathlib import Path

from fcode.chunking import Chunker
from fcode.contracts import FCodeConfig, IndexPhase, IndexState
from fcode.embeddings import EmbeddingEncoder, EXPECTED_DIMENSION
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.parser.python_ast import parse
from fcode.scanner.file_scanner import scan
from fcode.storage.fts_store import FTSStore
from fcode.storage.sqlite_store import SQLiteStore


SECRET = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"


class _FakeSentenceTransformer:
    constructor_calls = []
    encode_calls = 0

    def __init__(self, model_name, *, device, local_files_only):
        self.constructor_calls.append((model_name, device, local_files_only))

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **_kwargs):
        type(self).encode_calls += 1
        return [[0.01] * EXPECTED_DIMENSION for _ in texts]


class _Scanner:
    calls = 0

    def scan(self, repo, config):
        self.calls += 1
        return scan(repo, config)


class _Parser:
    def parse(self, scanned_file):
        return parse(scanned_file)


class _GraphBuilder:
    calls = 0

    def build(self, parsed_files):
        self.calls += 1
        return build_graph(parsed_files)


def _write_repository(root: Path) -> None:
    (root / "app.py").write_text(
        "from os import path\n\n"
        "class UserService:\n"
        "    def lookup_customer(self):\n"
        "        return 'customer-record'\n\n"
        "@app.get('/customers')\n"
        "def list_customers():\n"
        "    return UserService().lookup_customer()\n\n"
        f"API_TOKEN = '{SECRET}'\n",
        encoding="utf-8",
    )
    (root / "test_app.py").write_text(
        "from app import list_customers\n\ndef test_customers():\n    assert list_customers()\n",
        encoding="utf-8",
    )
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Observatory Handbook\n\n## Deployment Nebula\n\nUse the local command.\n",
        encoding="utf-8",
    )
    (root / "guide.rst").write_text(
        "Operations Atlas\n================\n\nRST evidence.\n",
        encoding="utf-8",
    )
    (root / "settings.toml").write_text(
        "\n".join([f"setting_{i} = 'value_{i}'" for i in range(120)] + ["feature_codename = 'quasar-switch'"]) + "\n",
        encoding="utf-8",
    )


def test_wp5_sqlite_fts_real_pipeline(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repository(repo)
    db_path = tmp_path / "index.db"

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    network_attempts = []

    def block_network(*args, **kwargs):
        network_attempts.append((args, kwargs))
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", block_network)
    _FakeSentenceTransformer.constructor_calls.clear()
    _FakeSentenceTransformer.encode_calls = 0

    scanner = _Scanner()
    graph_builder = _GraphBuilder()
    sqlite_store = SQLiteStore(str(db_path))
    sqlite_store.connect()
    fts_store = FTSStore(sqlite_store.conn)
    try:
        result = IndexService(
            scanner,
            _Parser(),
            Chunker(),
            encoder=EmbeddingEncoder(),
            graph_builder=graph_builder,
            sqlite_store=sqlite_store,
            fts_store=fts_store,
        ).build_through_sqlite_fts(FCodeConfig(repo_path=str(repo)))

        assert result.state_history == (
            IndexState.PENDING,
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
            IndexState.EMBEDDING,
            IndexState.GRAPHING,
            IndexState.STORING,
        )
        assert result.run_result.state == IndexState.STORING
        assert result.run_result.phase == IndexPhase.PERSIST
        assert result.completed_phase == IndexPhase.GRAPH
        assert result.persistent_replacement_started is True
        assert IndexState.COMPLETE not in result.state_history
        assert scanner.calls == graph_builder.calls == 1
        assert _FakeSentenceTransformer.encode_calls == 1
        assert _FakeSentenceTransformer.constructor_calls == [
            ("sentence-transformers/all-MiniLM-L6-v2", "cpu", True)
        ]
        assert network_attempts == []

        repo_id = sqlite_store.find_repository(str(repo.resolve()))
        assert repo_id
        conn = sqlite_store.conn
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        stored_chunks = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, file_id, content_hash, file_path FROM chunks WHERE repo_id = ?",
                (repo_id,),
            )
        }
        assert set(stored_chunks) == {chunk.chunk_id for chunk in result.chunks}
        assert all(
            stored_chunks[chunk.chunk_id]["content_hash"] == chunk.content_hash
            and stored_chunks[chunk.chunk_id]["file_id"] == chunk.file_id
            and stored_chunks[chunk.chunk_id]["file_path"] == chunk.file_path
            for chunk in result.chunks
        )

        queries = {
            "function": "list_customers",
            "method": "lookup_customer",
            "route": "customers",
            "markdown": "Nebula",
            "config": "quasar",
        }
        query_results = {}
        for label, term in queries.items():
            hits = fts_store.search_chunks(conn, term, repo_id, 20)
            assert hits, term
            query_results[label] = [hit["id"] for hit in hits]
            assert all(hit["id"] in stored_chunks for hit in hits)
            assert all(hit["file_path"] == stored_chunks[hit["id"]]["file_path"] for hit in hits)
            assert all(hit["start_line"] and hit["end_line"] for hit in hits)
        assert fts_store.search_chunks(conn, "term-that-does-not-exist", repo_id) == []
        assert fts_store.search_chunks(conn, SECRET, repo_id) == []
        assert fts_store.search_chunks(conn, "list_customers", "other-repository") == []

        database_text = " ".join(
            str(value)
            for table in ("files", "symbols", "chunks")
            for row in conn.execute(f"SELECT * FROM {table}")
            for value in row
            if value is not None
        )
        assert SECRET not in database_text
        assert sqlite_store.count_vectors(repo_id) == 0
        assert sqlite_store.count_graph_nodes(repo_id) == 0
        assert sqlite_store.count_graph_edges(repo_id) == 0
        status = sqlite_store.read_index_status(repo_id)
        assert status["status"] == "storing"
        assert status["total_vectors"] == 0
        assert not (repo / ".fcode" / "chroma").exists()
        print("STEP4_EVIDENCE=", {
            "in_memory": {
                "files": len(result.scan_result.files),
                "parsed": len(result.parsed_files),
                "chunks": len(result.chunks),
                "graph_nodes": result.graph_result.node_count,
                "graph_edges": result.graph_result.edge_count,
            },
            "sqlite": {
                "repositories": 1,
                "files": sqlite_store.count_files(repo_id),
                "symbols": sqlite_store.count_symbols(repo_id),
                "routes": conn.execute(
                    "SELECT COUNT(*) FROM symbols WHERE repo_id = ? AND symbol_type = 'route'",
                    (repo_id,),
                ).fetchone()[0],
                "chunks": sqlite_store.count_chunks(repo_id),
                "fts_chunks": fts_store.count_chunks_fts(conn),
                "vectors": sqlite_store.count_vectors(repo_id),
                "graph_nodes": sqlite_store.count_graph_nodes(repo_id),
                "graph_edges": sqlite_store.count_graph_edges(repo_id),
            },
            "queries": query_results,
            "model": _FakeSentenceTransformer.constructor_calls,
            "encoder_calls": _FakeSentenceTransformer.encode_calls,
            "network_attempts": len(network_attempts),
        })
    finally:
        sqlite_store.close()
