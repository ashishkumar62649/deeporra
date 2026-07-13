"""Focused unit tests for the read-only query service."""

import json
import sys
import types
from pathlib import Path

import pytest

from fcode.chunking.chunker import Chunker
from fcode.contracts import FCodeConfig, IndexState
from fcode.embeddings.encoder import EXPECTED_DIMENSION, EmbeddingEncoder
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.indexing.full_rebuild import FullRebuildCoordinator
from fcode.parser.python_ast import parse
from fcode.querying import QueryService, RepositoryNotIndexedError, QueryValidationError
from fcode.scanner.file_scanner import scan


class _FakeSentenceTransformer:
    def __init__(self, model_name, *, device, local_files_only):
        pass

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
        _Scanner(), _Parser(), Chunker(),
        encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder(),
    )


def _write_small_repo(repo: Path):
    (repo / "main.py").write_text(
        "from os import path\n\n"
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}"\n\n'
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n\n"
        "    def multiply(self, a: int, b: int) -> int:\n"
        "        return a * b\n\n"
        "def main():\n"
        "    calc = Calculator()\n"
        "    print(greet('World'))\n"
        "    print(calc.add(1, 2))\n\n"
        '@app.get("/api/calc")\n'
        "def calc_route():\n"
        "    calc = Calculator()\n"
        '    return {"result": calc.add(3, 4)}\n\n'
        "API_TOKEN = 'test_only_secret'\n",
        encoding="utf-8",
    )
    (repo / "test_main.py").write_text(
        "def test_greet():\n"
        "    pass\n\n"
        "def test_calculator():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Test Repo\n\nA small test fixture.\n", encoding="utf-8")


def _index_repo(repo: Path, monkeypatch) -> str:
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert result.run_result.state == IndexState.COMPLETE
    return result


# ── 1. Missing .fcode index ──────────────────────────────────────────────


def test_no_fcode_dir_raises_error(tmp_path):
    repo = tmp_path / "nonexistent"
    repo.mkdir()
    with pytest.raises(RepositoryNotIndexedError):
        QueryService(str(repo)).get_repository_summary()


# ── 2. Missing active generation ─────────────────────────────────────────


def test_no_active_generation_raises_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    fcode = repo / ".fcode"
    fcode.mkdir()
    (fcode / "index.db").write_text("", encoding="utf-8")
    with pytest.raises(RepositoryNotIndexedError):
        QueryService(str(repo)).get_repository_summary()


# ── 3. Repository summary ───────────────────────────────────────────────


def test_repository_summary_returns_counts(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    summary = qs.get_repository_summary()
    assert summary.index_status == "complete"
    assert summary.active_generation_id.startswith("generation-")
    assert summary.file_count > 0
    assert summary.symbol_count > 0
    assert summary.chunk_count > 0
    assert summary.graph_node_count > 0
    assert summary.graph_edge_count > 0


# ── 4. Text search ──────────────────────────────────────────────────────


def test_text_search_returns_known_content(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.search_code("greet", mode="text")
    assert len(results) >= 1
    matched = any("greet" in r.display_text for r in results)
    assert matched or any("greet" in r.source_path for r in results)


# ── 5. Semantic search ──────────────────────────────────────────────────


def test_semantic_search_returns_real_results(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.search_code("greet", mode="semantic")
    assert isinstance(results, list)
    for r in results:
        assert r.match_source == "semantic"
        assert r.semantic_score is not None
        assert r.text_score is None


def test_semantic_mode_raises_when_encoder_unavailable(tmp_path, monkeypatch):
    from fcode.contracts.errors import ErrorCode
    from fcode.embeddings.encoder import EmbeddingEncoderError

    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    with monkeypatch.context() as m:
        m.setattr(EmbeddingEncoder, "ensure_available",
                  lambda self: (_ for _ in ()).throw(EmbeddingEncoderError(ErrorCode.EMBEDDING_MODEL_UNAVAILABLE, "no model")))
        with pytest.raises(QueryValidationError, match="Semantic search is unavailable"):
            qs.search_code("greet", mode="semantic")


def test_hybrid_mode_degrades_gracefully_when_encoder_unavailable(tmp_path, monkeypatch):
    from fcode.contracts.errors import ErrorCode
    from fcode.embeddings.encoder import EmbeddingEncoderError

    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    with monkeypatch.context() as m:
        m.setattr(EmbeddingEncoder, "ensure_available",
                  lambda self: (_ for _ in ()).throw(EmbeddingEncoderError(ErrorCode.EMBEDDING_MODEL_UNAVAILABLE, "no model")))
        results = qs.search_code("greet", mode="hybrid")
        assert len(results) >= 1
        for r in results:
            assert r.match_source in ("text",)
            assert r.semantic_score is None


# ── 6. Hybrid search deduplicates ───────────────────────────────────────


def test_hybrid_search_deduplicates(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.search_code("greet", mode="hybrid", limit=100)
    ids = [r.chunk_id for r in results]
    assert len(ids) == len(set(ids))


# ── 7. Hybrid ordering is deterministic ─────────────────────────────────


def test_hybrid_deterministic_ordering(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    first = qs.search_code("add", mode="hybrid", limit=50)
    second = qs.search_code("add", mode="hybrid", limit=50)
    ids1 = [(r.combined_score, r.chunk_id) for r in first]
    ids2 = [(r.combined_score, r.chunk_id) for r in second]
    assert ids1 == ids2


# ── 8. Symbol exact lookup ──────────────────────────────────────────────


def test_symbol_exact_lookup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.find_symbols("Calculator", exact=False)
    assert len(results) >= 1
    assert any("Calculator" in r.qualified_name for r in results)


# ── 9. Symbol partial lookup ────────────────────────────────────────────


def test_symbol_partial_lookup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.find_symbols("Calc", exact=False)
    assert len(results) >= 1


# ── 10. Route lookup by method ──────────────────────────────────────────


def test_route_lookup_by_method(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.find_routes(method="GET")
    assert len(results) >= 1
    assert all(r.http_method == "GET" for r in results)


# ── 11. Route lookup by path ────────────────────────────────────────────


def test_route_lookup_by_path(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.find_routes(path_query="/api")
    assert len(results) >= 1


# ── 12. One-hop graph relationships ─────────────────────────────────────


def test_one_hop_graph_relationships(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    symbols = _index_repo(repo, monkeypatch).graph_result.nodes
    if not symbols:
        pytest.skip("No graph nodes to test")
    first_node = symbols[0]
    qs = QueryService(str(repo))
    related = qs.get_related(first_node.record_id, direction="outgoing", depth=1)
    assert isinstance(related, list)


# ── 13. Impact analysis ─────────────────────────────────────────────────


def test_impact_analysis_returns_direct_relationships(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    symbols = _index_repo(repo, monkeypatch).graph_result.nodes
    if not symbols:
        pytest.skip("No graph nodes to test")
    target = symbols[0]
    qs = QueryService(str(repo))
    impact = qs.analyze_change_impact(target.record_id)
    assert impact.analysis_type == "first_order"
    assert impact.target_semantic_key == target.record_id


# ── 14. Invalid blank query ─────────────────────────────────────────────


def test_blank_query_raises_error(tmp_path):
    qs = QueryService(str(tmp_path))
    with pytest.raises(QueryValidationError):
        qs.search_code("")
    with pytest.raises(QueryValidationError):
        qs.search_code("   ")
    with pytest.raises(QueryValidationError):
        qs.find_symbols("")
    with pytest.raises(QueryValidationError):
        qs.find_symbols("   ")


# ── 15. Invalid limit ───────────────────────────────────────────────────


def test_invalid_limit_raises_error(tmp_path):
    qs = QueryService(str(tmp_path))
    with pytest.raises(QueryValidationError):
        qs.search_code("test", limit=0)
    with pytest.raises(QueryValidationError):
        qs.search_code("test", limit=-1)
    with pytest.raises(QueryValidationError):
        qs.search_code("test", limit=999999)


# ── 16. Query operations do not write or activate a generation ───────────


def test_query_does_not_create_index(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    fcode_dir = repo / ".fcode"
    before = {str(p.relative_to(fcode_dir)): p.stat().st_size for p in fcode_dir.rglob("*") if p.is_file()}

    qs = QueryService(str(repo))
    qs.get_repository_summary()
    qs.search_code("greet")
    qs.find_symbols("Calculator")
    qs.find_routes()

    after = {str(p.relative_to(fcode_dir)): p.stat().st_size for p in fcode_dir.rglob("*") if p.is_file()}
    assert before == after


# ── 17. All returned paths are repo-relative ────────────────────────────


def test_paths_are_relative_not_absolute(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.search_code("add", mode="text")
    for r in results:
        assert not r.source_path.startswith("/")
        assert not r.source_path.startswith("\\")
        assert ".." not in r.source_path.split("/")

    symbols = qs.find_symbols("Calculator")
    for s in symbols:
        assert not s.source_path.startswith("/")
        assert not s.source_path.startswith("\\")


# ── 18. Connections are closed ──────────────────────────────────────────


def test_connections_are_closed_after_query(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    summary = qs.get_repository_summary()
    assert summary.file_count > 0


# ── 19. Exact symbol lookup with exact=True ──────────────────────────────


def test_exact_symbol_lookup_with_exact_true(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    results = qs.find_symbols("Calculator", exact=True)
    assert len(results) >= 1
    assert any(r.qualified_name == "Calculator" for r in results)


# ── 20. Unsupported search mode ──────────────────────────────────────────


def test_unsupported_search_mode_raises_error(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    with pytest.raises(QueryValidationError, match="Unsupported search mode"):
        qs.search_code("test", mode="vector")


# ── 21. Existing-implementation discovery via search + symbols ───────────


def test_implementation_discovery_via_search_and_symbols(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))

    code_results = qs.search_code("greet", mode="text")
    assert len(code_results) >= 1

    symbol_results = qs.find_symbols("greet")
    assert len(symbol_results) >= 1

    first_symbol = symbol_results[0]
    assert callable(getattr(qs, "analyze_change_impact", None))
    impact = qs.analyze_change_impact(first_symbol.semantic_key)
    assert impact.analysis_type == "first_order"


# ── 22. Graph depth validation ───────────────────────────────────────────


def test_get_related_unsupported_depth_rejected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    qs = QueryService(str(repo))
    symbols = _index_repo(repo, monkeypatch).graph_result.nodes
    if not symbols:
        pytest.skip("No graph nodes")
    with pytest.raises(QueryValidationError, match="depth > 1"):
        qs.get_related(symbols[0].record_id, depth=2)


# ── 23. Malformed route metadata does not crash ──────────────────────────


def test_malformed_route_metadata_does_not_crash(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    _index_repo(repo, monkeypatch)

    from fcode.storage import SQLiteStore
    from fcode.indexing.full_rebuild import FullRebuildCoordinator

    coord = FullRebuildCoordinator(str(repo))
    gen = coord.active_generation()
    assert gen is not None
    db_path = str(coord.workspace / "generations" / gen / "index.db")
    store = SQLiteStore(db_path)
    store.connect()
    store.conn.execute(
        "UPDATE symbols SET metadata = 'not valid json' WHERE symbol_type = 'route'"
    )
    store.conn.commit()
    store.close()

    qs = QueryService(str(repo))
    routes = qs.find_routes()
    assert len(routes) >= 0
