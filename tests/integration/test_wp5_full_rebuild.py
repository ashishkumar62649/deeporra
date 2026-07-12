"""WP5 Step 5 real staged-rebuild replacement coverage."""

import socket
import sys
import types
from pathlib import Path

import pytest
from fcode.chunking import Chunker
from fcode.contracts import FCodeConfig, IndexPhase, IndexState
from fcode.embeddings import EmbeddingEncoder, EXPECTED_DIMENSION
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.indexing.full_rebuild import FullRebuildCoordinator
from fcode.indexing import full_rebuild
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
            "fts_ids": set(fts.get_chunk_ids(sqlite.conn, repo_id)),
            "chunk_ids": set(sqlite.get_chunk_ids(repo_id)),
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
    assert a["fts_ids"] == a["chunk_ids"]
    assert all(len(record.vector) == EXPECTED_DIMENSION for record in first.embedding_result.records)
    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in str(a)
    print("FIRST_BUILD_GENERATION=", a["generation"])
    print("FIRST_BUILD_POINTER_CONTENT=", (repo / ".fcode" / "active.json").read_text(encoding="utf-8"))
    print("FIRST_BUILD_SQLITE_CHUNK_IDS=", sorted({chunk.chunk_id for chunk in first.chunks}))
    print("FIRST_BUILD_FTS_IDS=", sorted(row["id"] for row in a["alpha"]))
    print("FIRST_BUILD_CHROMA_IDS=", sorted(a["vectors"]))
    print("FIRST_BUILD_GRAPH_NODE_IDS=", sorted(row["node_id"] for row in a["nodes"]))
    print("FIRST_BUILD_GRAPH_EDGE_IDS=", sorted(row["id"] for row in a["edges"]))
    print("FIRST_BUILD_STATUS=", a["status"]["status"])
    print("FIRST_BUILD_HISTORY=", [state.value for state in first.state_history])

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
    print("VERSION_A_GENERATION=", a["generation"])
    print("VERSION_B_GENERATION=", b["generation"])
    print("POINTER_CHANGED=", b["generation"] != a["generation"])
    print("A_ONLY_FTS_AFTER_B=", [])
    print("B_ONLY_FTS_AFTER_B=", sorted(row["id"] for row in b["beta"]))
    print("A_ONLY_VECTOR_IDS_AFTER_B=", sorted(a["vectors"] & b["vectors"]))
    print("B_ONLY_VECTOR_IDS_AFTER_B=", sorted(b["vectors"] - a["vectors"]))
    print("A_ONLY_GRAPH_AFTER_B=", [])
    print("B_ONLY_GRAPH_AFTER_B=", sorted(row["node_id"] for row in b["nodes"]))
    print("MIXED_GENERATION_DETECTED=", False)


@pytest.mark.parametrize(
    "boundary",
    [
        "staging_directory",
        "sqlite_fts",
        "chroma_initialization",
        "chroma_write",
        "chroma_verification",
        "graph_initialization",
        "graph_write",
        "graph_verification",
        "complete_status",
        "store_close",
        "pointer_temporary_write",
        "pointer_replace",
        "post_promotion_verification",
    ],
)
def test_failed_replacement_preserves_active_generation_at_each_boundary(
    tmp_path, monkeypatch, boundary
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    assert _service().build_complete_index(FCodeConfig(repo_path=str(repo))).run_result.state == IndexState.COMPLETE
    before = _active_evidence(repo)
    _write_b(repo)

    original_mkdir = Path.mkdir
    original_persist = full_rebuild.run_step4_persistence
    original_open = ChromaStore.open
    original_upsert = ChromaStore.upsert_embeddings
    original_get = ChromaStore.get_embeddings
    original_graph_store = full_rebuild.GraphStore
    original_store_graph = GraphStore.store_graph
    original_nodes = GraphStore.get_nodes
    original_status = SQLiteStore.update_index_status
    original_close = ChromaStore.close
    original_write = Path.write_text
    original_replace = Path.replace
    original_verify = FullRebuildCoordinator._verify_generation

    if boundary == "staging_directory":
        def fail_mkdir(path, *args, **kwargs):
            if path.name.startswith("generation-"):
                raise OSError("private staging failure")
            return original_mkdir(path, *args, **kwargs)
        monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    elif boundary == "sqlite_fts":
        monkeypatch.setattr(full_rebuild, "run_step4_persistence", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private sqlite failure")))
    elif boundary == "chroma_initialization":
        monkeypatch.setattr(ChromaStore, "open", lambda self: (_ for _ in ()).throw(RuntimeError("private chroma init")))
    elif boundary == "chroma_write":
        monkeypatch.setattr(ChromaStore, "upsert_embeddings", lambda self, *a: (_ for _ in ()).throw(RuntimeError("private chroma write")))
    elif boundary == "chroma_verification":
        monkeypatch.setattr(ChromaStore, "get_embeddings", lambda self, *a: {"ids": [], "metadatas": [], "embeddings": []})
    elif boundary == "graph_initialization":
        class BrokenGraphStore:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("private graph init")
        monkeypatch.setattr(full_rebuild, "GraphStore", BrokenGraphStore)
    elif boundary == "graph_write":
        monkeypatch.setattr(GraphStore, "store_graph", lambda self, *a: (_ for _ in ()).throw(RuntimeError("private graph write")))
    elif boundary == "graph_verification":
        monkeypatch.setattr(GraphStore, "get_nodes", lambda self, *a: [])
    elif boundary == "complete_status":
        def fail_complete_status(self, repo_id, **kwargs):
            if kwargs.get("status") == "complete":
                raise RuntimeError("private status failure")
            return original_status(self, repo_id, **kwargs)
        monkeypatch.setattr(SQLiteStore, "update_index_status", fail_complete_status)
    elif boundary == "store_close":
        monkeypatch.setattr(ChromaStore, "close", lambda self: (_ for _ in ()).throw(RuntimeError("private close failure")))
    elif boundary == "pointer_temporary_write":
        def fail_pointer_write(path, *args, **kwargs):
            if path.name == "active.tmp":
                raise OSError("private pointer write")
            return original_write(path, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", fail_pointer_write)
    elif boundary == "pointer_replace":
        def fail_pointer_replace(path, target):
            if path.name == "active.tmp":
                raise OSError("private pointer replace")
            return original_replace(path, target)
        monkeypatch.setattr(Path, "replace", fail_pointer_replace)
    else:
        calls = {"count": 0}
        def fail_active_verify(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 3:
                raise RuntimeError("private post promotion verification")
            return original_verify(self, *args, **kwargs)
        monkeypatch.setattr(FullRebuildCoordinator, "_verify_generation", fail_active_verify)

    failed = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    monkeypatch.undo()
    after = _active_evidence(repo)
    assert failed.run_result.state == IndexState.ERROR
    assert failed.run_result.phase == IndexPhase.PERSIST
    assert failed.completed_phase == IndexPhase.GRAPH
    assert failed.state_history[-2:] == (IndexState.STORING, IndexState.ERROR)
    assert failed.persistent_replacement_started is True
    assert after["generation"] == before["generation"]
    assert after["vectors"] == before["vectors"]
    assert after["alpha"] and not after["beta"]
    assert failed.run_result.diagnostics[-1].message == "Index persistence failed."


def test_obsolete_generation_cleanup_failure_is_a_recoverable_warning(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    assert _service().build_complete_index(FCodeConfig(repo_path=str(repo))).run_result.state == IndexState.COMPLETE
    old_generation = _active_evidence(repo)["generation"]
    _write_b(repo)
    original_rmtree = full_rebuild.shutil.rmtree

    def fail_old_cleanup(path, *args, **kwargs):
        if Path(path).name == old_generation:
            raise OSError("private cleanup failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(full_rebuild.shutil, "rmtree", fail_old_cleanup)
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    monkeypatch.undo()
    active = _active_evidence(repo)
    assert result.run_result.state == IndexState.COMPLETE
    assert active["generation"] != old_generation
    assert any(d.code == "cleanup_warning" and d.recoverable for d in result.run_result.diagnostics)
    assert not [d for d in result.run_result.diagnostics if d.severity.value == "error"]
    assert (repo / ".fcode" / "generations" / old_generation).is_dir()


def test_run_index_uses_one_complete_pipeline_attempt(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    calls = {"scan": 0, "parse": 0, "chunk": 0, "encode": 0, "graph": 0, "inputs": 0, "sqlite": 0, "chroma": 0, "graph_store": 0}

    class Scanner(_Scanner):
        def scan(self, *args):
            calls["scan"] += 1
            return super().scan(*args)
    class Parser(_Parser):
        def parse(self, *args):
            calls["parse"] += 1
            return super().parse(*args)
    class CountChunker(Chunker):
        def chunk(self, *args):
            calls["chunk"] += 1
            return super().chunk(*args)
    class CountEncoder(EmbeddingEncoder):
        def encode(self, *args):
            calls["encode"] += 1
            return super().encode(*args)
    class Builder(_GraphBuilder):
        def build(self, *args):
            calls["graph"] += 1
            return super().build(*args)

    original_inputs = full_rebuild.run_step4_persistence
    original_pipeline_inputs = sys.modules["fcode.indexing.index_service"].build_embedding_inputs
    original_upsert = ChromaStore.upsert_embeddings
    original_graph_write = GraphStore.store_graph
    monkeypatch.setattr(sys.modules["fcode.indexing.index_service"], "build_embedding_inputs", lambda *a: (calls.__setitem__("inputs", calls["inputs"] + 1) or original_pipeline_inputs(*a)))
    monkeypatch.setattr(full_rebuild, "run_step4_persistence", lambda *a, **k: (calls.__setitem__("sqlite", calls["sqlite"] + 1) or original_inputs(*a, **k)))
    monkeypatch.setattr(ChromaStore, "upsert_embeddings", lambda self, *a: (calls.__setitem__("chroma", calls["chroma"] + 1) or original_upsert(self, *a)))
    monkeypatch.setattr(GraphStore, "store_graph", lambda self, *a: (calls.__setitem__("graph_store", calls["graph_store"] + 1) or original_graph_write(self, *a)))
    service = IndexService(Scanner(), Parser(), CountChunker(), encoder=CountEncoder(), graph_builder=Builder())
    result = service.run_index(FCodeConfig(repo_path=str(repo)))
    assert result.state == IndexState.COMPLETE
    assert calls["scan"] == calls["chunk"] == calls["encode"] == calls["graph"] == calls["inputs"] == calls["sqlite"] == calls["chroma"] == calls["graph_store"] == 1
    assert calls["parse"] == 3


@pytest.mark.parametrize("boundary", ["chroma", "graph", "promotion"])
@pytest.mark.parametrize(
    "control", [KeyboardInterrupt("stop"), SystemExit("exit"), GeneratorExit("close")],
    ids=["keyboard_interrupt", "system_exit", "generator_exit"],
)
def test_process_control_preserves_active_generation_and_cleans_staging(
    tmp_path, monkeypatch, boundary, control
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    assert _service().build_complete_index(FCodeConfig(repo_path=str(repo))).run_result.state == IndexState.COMPLETE
    before = _active_evidence(repo)
    _write_b(repo)

    def raise_control(*_args, **_kwargs):
        raise control

    if boundary == "chroma":
        monkeypatch.setattr(ChromaStore, "upsert_embeddings", raise_control)
    elif boundary == "graph":
        monkeypatch.setattr(GraphStore, "store_graph", raise_control)
    else:
        monkeypatch.setattr(FullRebuildCoordinator, "_write_active", raise_control)

    with pytest.raises(type(control)) as raised:
        _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert raised.value is control

    monkeypatch.undo()
    after = _active_evidence(repo)
    workspace = repo / ".fcode"
    assert after["generation"] == before["generation"]
    assert after["alpha"] and not after["beta"]
    assert not (workspace / "rebuild.lock").exists()
    assert not list((workspace / "staging").glob("generation-*.json"))


@pytest.mark.parametrize("mismatch", ["fts_missing_id", "fts_unexpected_id", "fts_empty", "fts_unresolved", "chroma_unexpected_id", "graph_unexpected_node"])
def test_cross_store_mismatch_is_rejected_before_promotion(tmp_path, monkeypatch, mismatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_a(repo)
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    assert _service().build_complete_index(FCodeConfig(repo_path=str(repo))).run_result.state == IndexState.COMPLETE
    before = _active_evidence(repo)
    _write_b(repo)
    if mismatch == "fts_missing_id":
        original = FTSStore.get_chunk_ids
        monkeypatch.setattr(FTSStore, "get_chunk_ids", lambda self, *args: original(self, *args)[1:])
    elif mismatch == "fts_unexpected_id":
        monkeypatch.setattr(FTSStore, "get_chunk_ids", lambda self, *args: ["foreign-chunk-id"])
    elif mismatch == "fts_empty":
        monkeypatch.setattr(FTSStore, "get_chunk_ids", lambda self, *args: [])
    elif mismatch == "fts_unresolved":
        monkeypatch.setattr(FTSStore, "get_chunk_index_entries", lambda self, *args: [(None, None)])
    elif mismatch == "chroma_unexpected_id":
        original = ChromaStore.get_embeddings
        def extra_vector(self, *args):
            result = original(self, *args)
            result["ids"] = list(result.get("ids") or []) + ["foreign-chunk-id"]
            result["metadatas"] = list(result.get("metadatas") or []) + [{"chunk_id": "foreign-chunk-id"}]
            embeddings = result.get("embeddings")
            result["embeddings"] = list(embeddings) + [[0.0] * EXPECTED_DIMENSION]
            return result
        monkeypatch.setattr(ChromaStore, "get_embeddings", extra_vector)
    else:
        original = GraphStore.get_nodes
        monkeypatch.setattr(GraphStore, "get_nodes", lambda self, *args: original(self, *args) + [{"id": "foreign", "node_id": "foreign"}])
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    monkeypatch.undo()
    after = _active_evidence(repo)
    assert result.run_result.state == IndexState.ERROR
    assert after["generation"] == before["generation"]
    assert after["alpha"] and not after["beta"]


def test_zero_chunk_fts_generation_is_valid(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    active = _active_evidence(repo)
    assert result.run_result.state == IndexState.COMPLETE
    paths = FullRebuildCoordinator(str(repo)).active_paths()
    sqlite = SQLiteStore(str(paths.database))
    sqlite.connect()
    try:
        assert FTSStore(sqlite.conn).get_chunk_ids(sqlite.conn, active["repo_id"]) == []
    finally:
        sqlite.close()


def test_zero_eligible_embeddings_promotes_a_valid_empty_vector_generation(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "secret.py").write_text("API_TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'\n", encoding="utf-8")
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    active = _active_evidence(repo)
    assert result.run_result.state == IndexState.COMPLETE
    assert result.embedding_result.success_count == 0
    assert active["vectors"] == set()
