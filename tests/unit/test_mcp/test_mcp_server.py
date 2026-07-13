"""Focused unit tests for the MCP server creation, tools, and error handling."""

import json

import pytest

from fcode.mcp_server import create_mcp_server
from fcode.querying import (
    CodeSearchResult,
    ImpactAnalysis,
    QueryValidationError,
    RelatedNode,
    RepositoryNotIndexedError,
    RouteRecord,
    SymbolRecord,
)


def _make_server():
    return create_mcp_server()


def _tool_names(server):
    return list(server._tool_manager._tools.keys())


def _tool_meta(server, name):
    return server._tool_manager._tools.get(name)


EXPECTED_TOOLS = [
    "repository_summary",
    "search_code",
    "find_symbols",
    "find_routes",
    "get_related_code",
    "analyze_change_impact",
    "find_existing_implementation",
]


def test_server_creation():
    server = _make_server()
    assert server.name == "fcode-mcp"
    assert server.instructions is not None


def test_all_tools_registered():
    server = _make_server()
    names = _tool_names(server)
    for name in EXPECTED_TOOLS:
        assert name in names
    assert len(names) == len(EXPECTED_TOOLS)


def test_repository_summary_schema(server=_make_server()):
    meta = _tool_meta(server, "repository_summary")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters


def test_search_code_schema():
    server = _make_server()
    meta = _tool_meta(server, "search_code")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "query" in sig.parameters
    assert "mode" in sig.parameters
    assert "limit" in sig.parameters


def test_find_symbols_schema():
    server = _make_server()
    meta = _tool_meta(server, "find_symbols")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "query" in sig.parameters
    assert "exact" in sig.parameters
    assert "limit" in sig.parameters


def test_find_routes_schema():
    server = _make_server()
    meta = _tool_meta(server, "find_routes")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "method" in sig.parameters
    assert "path_query" in sig.parameters
    assert "handler_query" in sig.parameters
    assert "limit" in sig.parameters


def test_get_related_code_schema():
    server = _make_server()
    meta = _tool_meta(server, "get_related_code")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "semantic_key" in sig.parameters
    assert "direction" in sig.parameters
    assert "edge_types" in sig.parameters
    assert "depth" in sig.parameters
    assert "limit" in sig.parameters


def test_analyze_change_impact_schema():
    server = _make_server()
    meta = _tool_meta(server, "analyze_change_impact")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "semantic_key" in sig.parameters
    assert "limit" in sig.parameters


def test_find_existing_implementation_schema():
    server = _make_server()
    meta = _tool_meta(server, "find_existing_implementation")
    assert meta is not None
    import inspect
    sig = inspect.signature(meta.fn)
    assert "repository_root" in sig.parameters
    assert "query" in sig.parameters
    assert "limit" in sig.parameters


def test_repository_summary_delegates(monkeypatch):
    from fcode.querying import RepositorySummary
    fake_summary = RepositorySummary(
        repository_root="/fake", active_generation_id="gen-1",
        index_status="complete", indexed_at="2024-01-01T00:00:00",
        file_count=10, parsed_count=8, not_applicable_count=1, error_count=1,
        symbol_count=20, import_count=5, route_count=2, test_count=3,
        chunk_count=15, graph_node_count=30, graph_edge_count=25,
        warning_count=2, fatal_error_count=0,
    )
    class _FakeQS:
        def get_repository_summary(self):
            return fake_summary
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", lambda root: _FakeQS())
    server = _make_server()
    result_str = server._tool_manager._tools["repository_summary"].fn(repository_root="/fake")
    data = json.loads(result_str)
    assert data["index_status"] == "complete"
    assert data["file_count"] == 10
    assert data["symbol_count"] == 20


def test_search_code_text_delegates(monkeypatch):
    fake_results = [CodeSearchResult(
        chunk_id="c1", source_path="main.py", start_line=1, end_line=10,
        chunk_kind="function", owner_semantic_key="func1",
        display_text="def greet():", text_score=0.9, semantic_score=None,
        combined_score=0.9, match_source="text",
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode): return fake_results
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["search_code"].fn(
        repository_root="/fake", query="greet", mode="text", limit=10)
    data = json.loads(result_str)
    assert len(data) == 1
    assert data[0]["chunk_id"] == "c1"
    assert data[0]["match_source"] == "text"


def test_semantic_unavailable_error_propagates(monkeypatch):
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode):
            raise QueryValidationError("Semantic search is unavailable: the embedding model could not be loaded.")
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    with pytest.raises(QueryValidationError, match="Semantic search is unavailable"):
        server._tool_manager._tools["search_code"].fn(
            repository_root="/fake", query="greet", mode="semantic", limit=10)


def test_hybrid_degraded_text_only(monkeypatch):
    fake_results = [CodeSearchResult(
        chunk_id="c1", source_path="main.py", start_line=1, end_line=10,
        chunk_kind="function", owner_semantic_key="func1",
        display_text="def greet():", text_score=0.9, semantic_score=None,
        combined_score=0.9, match_source="text",
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode): return fake_results
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["search_code"].fn(
        repository_root="/fake", query="greet", mode="hybrid", limit=10)
    data = json.loads(result_str)
    assert all(r["match_source"] == "text" for r in data)
    assert all(r["semantic_score"] is None for r in data)


def test_find_symbols_delegates(monkeypatch):
    fake_symbols = [SymbolRecord(
        semantic_key="s1", kind="function", qualified_name="Calculator.add",
        source_path="main.py", start_line=5, end_line=8, parent_semantic_key="Calculator",
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def find_symbols(self, query, exact, limit): return fake_symbols
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["find_symbols"].fn(
        repository_root="/fake", query="add", exact=False, limit=20)
    data = json.loads(result_str)
    assert data[0]["qualified_name"] == "Calculator.add"


def test_find_routes_delegates(monkeypatch):
    fake_routes = [RouteRecord(
        http_method="GET", route_path="/api/calc", handler_semantic_key="calc_route",
        handler_name="calc_route", source_path="main.py", decorator_line=68,
        handler_start_line=69, handler_end_line=72,
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def find_routes(self, method, path_query, handler_query, limit): return fake_routes
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["find_routes"].fn(
        repository_root="/fake", method="GET", path_query="", handler_query="", limit=50)
    data = json.loads(result_str)
    assert data[0]["http_method"] == "GET"


def test_get_related_code_delegates(monkeypatch):
    fake_related = [RelatedNode(
        center_identity="n1", related_node_identity="n2", node_kind="function",
        qualified_name="some_func", source_path="main.py", relationship_type="calls",
        direction="outgoing", qualifier=None,
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def get_related(self, semantic_key, direction, edge_types, depth, limit): return fake_related
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["get_related_code"].fn(
        repository_root="/fake", semantic_key="n1", direction="outgoing", edge_types="", depth=1, limit=100)
    data = json.loads(result_str)
    assert data[0]["relationship_type"] == "calls"


def test_analyze_change_impact_delegates(monkeypatch):
    fake_impact = ImpactAnalysis(
        target_semantic_key="n1", target_kind="function", target_qualified_name="greet",
        target_source_path="main.py", analysis_type="first_order",
    )
    class _FakeQS:
        def __init__(self, root): self.root = root
        def analyze_change_impact(self, semantic_key, limit): return fake_impact
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["analyze_change_impact"].fn(
        repository_root="/fake", semantic_key="n1", limit=100)
    data = json.loads(result_str)
    assert data["analysis_type"] == "first_order"


def test_find_existing_implementation_composes(monkeypatch):
    fake_code = [CodeSearchResult(
        chunk_id="c1", source_path="main.py", start_line=1, end_line=10,
        chunk_kind="function", owner_semantic_key="greet",
        display_text="def greet():", text_score=0.9, semantic_score=None,
        combined_score=0.9, match_source="text",
    )]
    fake_symbols = [SymbolRecord(
        semantic_key="s1", kind="function", qualified_name="greet",
        source_path="main.py", start_line=1, end_line=4, parent_semantic_key=None,
    )]
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode): return fake_code
        def find_symbols(self, query, exact, limit): return fake_symbols
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    result_str = server._tool_manager._tools["find_existing_implementation"].fn(
        repository_root="/fake", query="greet", limit=10)
    data = json.loads(result_str)
    assert "code_results" in data
    assert "symbol_results" in data


def test_missing_index_error_propagates(monkeypatch):
    class _FakeQS:
        def __init__(self, root): self.root = root
        def get_repository_summary(self):
            raise RepositoryNotIndexedError("Repository at /fake has no active index.")
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    with pytest.raises(RepositoryNotIndexedError):
        server._tool_manager._tools["repository_summary"].fn(repository_root="/fake")


def test_invalid_query_error_propagates(monkeypatch):
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode):
            raise QueryValidationError("Query must not be blank.")
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    with pytest.raises(QueryValidationError):
        server._tool_manager._tools["search_code"].fn(
            repository_root="/fake", query="", mode="text", limit=10)


def test_invalid_limit_error_propagates(monkeypatch):
    class _FakeQS:
        def __init__(self, root): self.root = root
        def search_code(self, query, limit, mode):
            raise QueryValidationError("Limit must be a positive integer.")
    monkeypatch.setattr("fcode.mcp_server.server.QueryService", _FakeQS)
    server = _make_server()
    with pytest.raises(QueryValidationError):
        server._tool_manager._tools["search_code"].fn(
            repository_root="/fake", query="greet", mode="text", limit=0)
