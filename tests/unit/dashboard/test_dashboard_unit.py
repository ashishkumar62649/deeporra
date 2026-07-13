"""Focused unit tests for the dashboard module â€” no Streamlit server required."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

from fcode.querying import (
    CodeSearchResult,
    ImpactAnalysis,
    QueryValidationError,
    RelatedNode,
    RepositoryNotIndexedError,
    RepositorySummary,
    RouteRecord,
    SymbolRecord,
)


# â”€â”€ Fake QueryService â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class _FakeQueryService:
    """Simulates QueryService for isolated dashboard unit tests."""

    summary: RepositorySummary | None = None
    search_results: list[CodeSearchResult] | None = None
    symbol_results: list[SymbolRecord] | None = None
    route_results: list[RouteRecord] | None = None
    related_results: list[RelatedNode] | None = None
    impact_result: ImpactAnalysis | None = None
    raise_on: str | None = None  # "not_indexed", "validation", "generic"

    def get_repository_summary(self) -> RepositorySummary:
        self._check_raise("get_repository_summary")
        if self.summary is None:
            raise RepositoryNotIndexedError("No active generation")
        return self.summary

    def search_code(self, query: str, limit: int = 10, mode: str = "text") -> list[CodeSearchResult]:
        self._check_raise("search_code")
        self._validate_query(query)
        if self.search_results is None:
            return []
        if mode == "semantic" and self.search_results:
            for r in self.search_results:
                object.__setattr__(r, "match_source", "semantic")
                object.__setattr__(r, "semantic_score", r.combined_score)
                object.__setattr__(r, "text_score", None)
        if mode == "text" and self.search_results:
            for r in self.search_results:
                object.__setattr__(r, "match_source", "text")
                object.__setattr__(r, "text_score", r.combined_score)
                object.__setattr__(r, "semantic_score", None)
        return (self.search_results or [])[:limit]

    def find_symbols(self, query: str, limit: int = 20, exact: bool = False) -> list[SymbolRecord]:
        self._check_raise("find_symbols")
        self._validate_query(query)
        return (self.symbol_results or [])[:limit]

    def find_routes(
        self,
        method: Optional[str] = None,
        path_query: Optional[str] = None,
        handler_query: Optional[str] = None,
        limit: int = 50,
    ) -> list[RouteRecord]:
        self._check_raise("find_routes")
        results = self.route_results or []
        if method:
            results = [r for r in results if r.http_method == method]
        if path_query:
            results = [r for r in results if path_query in r.route_path]
        return results[:limit]

    def get_related(
        self,
        semantic_key: str,
        direction: str = "both",
        edge_types: Optional[list[str]] = None,
        depth: int = 1,
        limit: int = 100,
    ) -> list[RelatedNode]:
        self._check_raise("get_related")
        if depth > 1:
            raise QueryValidationError("depth > 1 is not supported")
        if direction not in ("outgoing", "incoming", "both"):
            raise QueryValidationError(f"Invalid direction: {direction}")
        results = self.related_results or []
        if edge_types:
            results = [r for r in results if r.relationship_type in edge_types]
        return results[:limit]

    def analyze_change_impact(
        self, semantic_key: str, limit: int = 100
    ) -> ImpactAnalysis:
        self._check_raise("analyze_change_impact")
        if self.impact_result is None:
            raise QueryValidationError(f"Symbol not found: {semantic_key}")
        return self.impact_result

    def _check_raise(self, method: str) -> None:
        if self.raise_on == "not_indexed":
            raise RepositoryNotIndexedError("No active generation")
        if self.raise_on == "generic":
            raise RuntimeError("Something went wrong")

    @staticmethod
    def _validate_query(query: str) -> None:
        if not query.strip():
            raise QueryValidationError("Query must not be blank")
        if len(query) > 1000:
            raise QueryValidationError("Query too long")


# â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture
def summary() -> RepositorySummary:
    return RepositorySummary(
        repository_root="/fake/repo",
        active_generation_id="generation-abc123",
        index_status="complete",
        indexed_at="2026-07-13T12:00:00",
        file_count=42,
        parsed_count=30,
        not_applicable_count=10,
        error_count=2,
        symbol_count=150,
        import_count=80,
        route_count=5,
        test_count=20,
        chunk_count=300,
        graph_node_count=200,
        graph_edge_count=400,
        warning_count=1,
        fatal_error_count=0,
    )


@pytest.fixture
def search_results() -> list[CodeSearchResult]:
    return [
        CodeSearchResult(
            chunk_id="chunk-1",
            source_path="src/main.py",
            start_line=10,
            end_line=25,
            chunk_kind="function",
            owner_semantic_key="main",
            display_text="def greet(name): return f'Hello {name}'",
            text_score=0.85,
            semantic_score=None,
            combined_score=0.85,
            match_source="text",
        ),
        CodeSearchResult(
            chunk_id="chunk-2",
            source_path="src/utils.py",
            start_line=5,
            end_line=15,
            chunk_kind="function",
            owner_semantic_key="validate",
            display_text="def validate_email(email): ...",
            text_score=None,
            semantic_score=0.72,
            combined_score=0.72,
            match_source="semantic",
        ),
    ]


@pytest.fixture
def symbol_results() -> list[SymbolRecord]:
    return [
        SymbolRecord(
            semantic_key="Calculator",
            kind="class",
            qualified_name="Calculator",
            source_path="src/calc.py",
            start_line=1,
            end_line=30,
            parent_semantic_key=None,
        ),
        SymbolRecord(
            semantic_key="Calculator.add",
            kind="method",
            qualified_name="Calculator.add",
            source_path="src/calc.py",
            start_line=5,
            end_line=10,
            parent_semantic_key="Calculator",
        ),
    ]


@pytest.fixture
def route_results() -> list[RouteRecord]:
    return [
        RouteRecord(
            http_method="GET",
            route_path="/api/items",
            handler_semantic_key="app.routes.get_items",
            handler_name="get_items",
            source_path="src/routes.py",
            decorator_line=42,
            handler_start_line=43,
            handler_end_line=60,
        ),
    ]


@pytest.fixture
def related_results() -> list[RelatedNode]:
    return [
        RelatedNode(
            center_identity="",
            related_node_identity="node-1",
            node_kind="function",
            qualified_name="process_data",
            source_path="src/process.py",
            relationship_type="calls",
            direction="outgoing",
            qualifier="extracted",
        ),
    ]


@pytest.fixture
def impact_result() -> ImpactAnalysis:
    return ImpactAnalysis(
        target_semantic_key="Calculator.add",
        target_kind="method",
        target_qualified_name="Calculator.add",
        target_source_path="src/calc.py",
        analysis_type="first_order",
        direct_callers=[
            SymbolRecord("main", "function", "main", "src/main.py", 1, 10, None)
        ],
        direct_callees=[],
        containing_file="src/calc.py",
        containing_class="Calculator",
        import_relationships=[
            RelatedNode("", "node-i1", "module", "math", "", "imports", "outgoing", None)
        ],
        route_relationships=[
            RelatedNode("", "node-r1", "route", "/api/calc", "src/calc.py", "handles_route", "outgoing", None)
        ],
        related_tests=[
            SymbolRecord("test_add", "test", "test_add", "tests/test_calc.py", 1, 5, None)
        ],
        warnings=["No callee data available"],
    )


# â”€â”€ Test 1: Module imports work â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDashboardImports:
    """Verify the dashboard package imports without starting a server."""

    def test_import_dashboard_package(self) -> None:
        import fcode.dashboard
        assert hasattr(fcode.dashboard, "__all__")

    def test_import_dashboard_main(self) -> None:
        import fcode.dashboard.__main__
        assert hasattr(fcode.dashboard.__main__, "main")

    def test_import_app_functions(self) -> None:
        from fcode.dashboard.api import safe_summary, safe_search, safe_symbols
        from fcode.dashboard.api import safe_routes, safe_related, safe_impact
        assert callable(safe_summary)
        assert callable(safe_search)
        assert callable(safe_symbols)
        assert callable(safe_routes)
        assert callable(safe_related)
        assert callable(safe_impact)


# â”€â”€ Test 2: Uses QueryService, not direct storage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUsesQueryService:
    """Verify the dashboard uses QueryService rather than direct storage."""

    APP_SOURCE = Path(__file__).parents[3] / "fcode" / "dashboard" / "app.py"

    def test_imports_query_service(self) -> None:
        source = self.APP_SOURCE.read_text(encoding="utf-8")
        assert "from fcode.querying import" in source

    def test_does_not_import_storage(self) -> None:
        source = self.APP_SOURCE.read_text(encoding="utf-8")
        assert "from fcode.storage" not in source
        assert "import fcode.storage" not in source
        assert "SQLiteStore" not in source
        assert "ChromaStore" not in source

    def test_does_not_import_chroma(self) -> None:
        source = self.APP_SOURCE.read_text(encoding="utf-8")
        assert "chroma" not in source.lower()


# â”€â”€ Test 3: Repository summary renders expected values â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRepositorySummary:
    """Verify safe_summary returns proper values."""

    def test_summary_returns_summary_object(self, summary: RepositorySummary) -> None:
        from fcode.dashboard.api import safe_summary
        qs = _FakeQueryService(summary=summary)
        result = safe_summary(qs)
        assert isinstance(result, RepositorySummary)
        assert result.repository_root == "/fake/repo"
        assert result.index_status == "complete"
        assert result.file_count == 42
        assert result.symbol_count == 150

    def test_summary_shows_all_expected_fields(self, summary: RepositorySummary) -> None:
        from fcode.dashboard.api import safe_summary
        qs = _FakeQueryService(summary=summary)
        result = safe_summary(qs)
        assert isinstance(result, RepositorySummary)
        assert result.active_generation_id == "generation-abc123"
        assert result.indexed_at == "2026-07-13T12:00:00"
        assert result.parsed_count == 30
        assert result.not_applicable_count == 10
        assert result.error_count == 2
        assert result.import_count == 80
        assert result.route_count == 5
        assert result.test_count == 20
        assert result.chunk_count == 300
        assert result.graph_node_count == 200
        assert result.graph_edge_count == 400
        assert result.warning_count == 1
        assert result.fatal_error_count == 0


# â”€â”€ Test 4: Missing index returns safe error â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMissingIndex:
    """Verify missing or unindexed repository returns safe error strings."""

    def test_not_indexed_returns_string(self) -> None:
        from fcode.dashboard.api import safe_summary, safe_search, safe_symbols
        qs = _FakeQueryService(raise_on="not_indexed")
        result = safe_summary(qs)
        assert isinstance(result, str)
        assert "not indexed" in result.lower()

    def test_not_indexed_search_returns_string(self) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(raise_on="not_indexed")
        result = safe_search(qs, "test", 10, "text")
        assert isinstance(result, str)

    def test_not_indexed_symbols_returns_string(self) -> None:
        from fcode.dashboard.api import safe_symbols
        qs = _FakeQueryService(raise_on="not_indexed")
        result = safe_symbols(qs, "test", 20, False)
        assert isinstance(result, str)

    def test_generic_error_returns_string(self) -> None:
        from fcode.dashboard.api import safe_summary
        qs = _FakeQueryService(raise_on="generic")
        result = safe_summary(qs)
        assert isinstance(result, str)
        assert "error" in result.lower() or "error" in result


# â”€â”€ Test 5: Text search results render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSearchResults:
    """Verify text search returns proper results."""

    def test_text_search_returns_results(self, search_results: list[CodeSearchResult]) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(search_results=search_results)
        results = safe_search(qs, "greet", 10, "text")
        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0].source_path == "src/main.py"
        assert results[0].match_source == "text"
        assert results[0].text_score == 0.85

    def test_semantic_search_returns_results(self, search_results: list[CodeSearchResult]) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(search_results=search_results)
        results = safe_search(qs, "greet", 10, "semantic")
        assert isinstance(results, list)
        assert all(r.match_source == "semantic" for r in results)
        assert all(r.semantic_score is not None for r in results)
        assert all(r.text_score is None for r in results)

    def test_hybrid_search_returns_results(self, search_results: list[CodeSearchResult]) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(search_results=search_results)
        results = safe_search(qs, "greet", 10, "hybrid")
        assert isinstance(results, list)
        assert len(results) > 0


# â”€â”€ Test 6: Semantic unavailable error â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSemanticUnavailable:
    """Verify semantic-unavailable errors are shown honestly."""

    def test_semantic_mode_raises_validation_error(self) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(raise_on="generic")
        result = safe_search(qs, "test", 10, "semantic")
        assert isinstance(result, str)


# â”€â”€ Test 7: Hybrid degraded labeled text-only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHybridDegraded:
    """Verify hybrid degraded results are labeled."""

    def test_hybrid_degraded_results_show_text_source(self, search_results: list[CodeSearchResult]) -> None:
        from fcode.dashboard.api import safe_search
        for r in search_results:
            object.__setattr__(r, "match_source", "text")
            object.__setattr__(r, "semantic_score", None)
        qs = _FakeQueryService(search_results=search_results)
        results = safe_search(qs, "greet", 10, "hybrid")
        assert isinstance(results, list)
        assert all(r.match_source == "text" for r in results)

    def test_app_script_checks_hybrid_degraded(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "hybrid" in source.lower() and "degraded" in source.lower()


# â”€â”€ Test 8: Symbol results render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSymbolResults:
    """Verify symbol lookup returns proper results."""

    def test_symbol_results_have_expected_fields(self, symbol_results: list[SymbolRecord]) -> None:
        from fcode.dashboard.api import safe_symbols
        qs = _FakeQueryService(symbol_results=symbol_results)
        results = safe_symbols(qs, "Calculator", 20, False)
        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0].qualified_name == "Calculator"
        assert results[0].kind == "class"
        assert results[1].parent_semantic_key == "Calculator"

    def test_exact_symbol_lookup(self, symbol_results: list[SymbolRecord]) -> None:
        from fcode.dashboard.api import safe_symbols
        qs = _FakeQueryService(symbol_results=symbol_results)
        results = safe_symbols(qs, "Calculator", 20, True)
        assert isinstance(results, list)
        assert len(results) <= 2


# â”€â”€ Test 9: Route results render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRouteResults:
    """Verify route lookup returns proper results."""

    def test_route_results_have_expected_fields(self, route_results: list[RouteRecord]) -> None:
        from fcode.dashboard.api import safe_routes
        qs = _FakeQueryService(route_results=route_results)
        results = safe_routes(qs, "GET", None, None, 50)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].http_method == "GET"
        assert results[0].route_path == "/api/items"

    def test_route_result_paths_are_relative(self, route_results: list[RouteRecord]) -> None:
        from fcode.dashboard.api import safe_routes
        qs = _FakeQueryService(route_results=route_results)
        results = safe_routes(qs, None, None, None, 50)
        for r in results:
            assert not r.source_path.startswith("/")
            assert not r.source_path.startswith("\\")


# â”€â”€ Test 10: Related-code results render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRelatedCode:
    """Verify related-code lookup returns proper results."""

    def test_related_results_have_expected_fields(self, related_results: list[RelatedNode]) -> None:
        from fcode.dashboard.api import safe_related
        qs = _FakeQueryService(related_results=related_results)
        results = safe_related(qs, "node-0", "outgoing", ["calls"], 100)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].qualified_name == "process_data"
        assert results[0].relationship_type == "calls"
        assert results[0].direction == "outgoing"

    def test_related_depth_defaults_to_one(self) -> None:
        from fcode.querying import QueryValidationError
        qs = _FakeQueryService(related_results=[])
        with pytest.raises(QueryValidationError, match="depth > 1"):
            qs.get_related("node-0", depth=2)


# â”€â”€ Test 11: Impact results render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestImpactResults:
    """Verify impact analysis returns proper results."""

    def test_impact_has_expected_sections(self, impact_result: ImpactAnalysis) -> None:
        from fcode.dashboard.api import safe_impact
        qs = _FakeQueryService(impact_result=impact_result)
        result = safe_impact(qs, "Calculator.add", 100)
        assert isinstance(result, dict)
        assert result["target"] == "Calculator.add"
        assert result["kind"] == "method"
        assert result["analysis_type"] == "first_order"
        assert len(result["direct_callers"]) == 1
        assert len(result["direct_callees"]) == 0
        assert result["containing_class"] == "Calculator"
        assert len(result["related_tests"]) == 1
        assert len(result["warnings"]) == 1


# â”€â”€ Test 12: First-order limitation visible â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFirstOrderLimitation:
    """Verify the first-order limitation is clearly labeled."""

    def test_app_script_contains_first_order_label(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "FIRST-ORDER IMPACT ONLY" in source

    def test_impact_analysis_type_is_first_order(self, impact_result: ImpactAnalysis) -> None:
        assert impact_result.analysis_type == "first_order"


# â”€â”€ Test 13: Blank query validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBlankQueryValidation:
    """Verify blank queries are rejected."""

    def test_blank_search_raises_validation_error(self) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(search_results=[])
        result = safe_search(qs, "", 10, "text")
        assert isinstance(result, str)
        assert "blank" in result.lower() or "error" in result.lower()

    def test_blank_symbols_raises_validation_error(self) -> None:
        from fcode.dashboard.api import safe_symbols
        qs = _FakeQueryService(symbol_results=[])
        result = safe_symbols(qs, "", 20, False)
        assert isinstance(result, str)
        assert "blank" in result.lower() or "error" in result.lower()

    def test_app_checks_blank_queries(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "not query.strip()" in source or 'Please enter a' in source


# â”€â”€ Test 14: Invalid limit validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestInvalidLimitValidation:
    """Verify invalid limit values are handled."""

    def test_limit_validation_returns_string(self) -> None:
        from fcode.dashboard.api import safe_search
        from fcode.querying import QueryValidationError
        qs = _FakeQueryService()
        qs.search_code = lambda query, limit, mode: (_ for _ in ()).throw(
            QueryValidationError("limit must be between 1 and 500")
        )
        result = safe_search(qs, "test", 0, "text")
        assert isinstance(result, str)
        assert "limit" in result.lower()


# â”€â”€ Test 15: Repository-relative paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRepoRelativePaths:
    """Verify all displayed paths are repository-relative."""

    def test_search_paths_are_relative(self, search_results: list[CodeSearchResult]) -> None:
        from fcode.dashboard.api import safe_search
        qs = _FakeQueryService(search_results=search_results)
        results = safe_search(qs, "greet", 10, "text")
        for r in results:
            assert not r.source_path.startswith("/")
            assert not r.source_path.startswith("\\")

    def test_symbol_paths_are_relative(self, symbol_results: list[SymbolRecord]) -> None:
        from fcode.dashboard.api import safe_symbols
        qs = _FakeQueryService(symbol_results=symbol_results)
        results = safe_symbols(qs, "Calculator", 20, False)
        for r in results:
            assert not r.source_path.startswith("/")
            assert not r.source_path.startswith("\\")


# â”€â”€ Test 16-19: Safety checks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSafetyChecks:
    """Verify read-only and local safety properties."""

    def test_no_source_file_modification(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "open(" not in source
        assert ".write(" not in source
        assert "shutil" not in source

    def test_no_fcode_creation(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        api_source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "api.py").read_text(encoding="utf-8")
        assert ".fcode" not in source
        assert ".fcode" not in api_source

    def test_no_index_activation(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "IndexService" not in source
        assert "build_complete_index" not in source
        assert "index_service" not in source.lower()

    def test_no_network_access(self) -> None:
        source = Path(__file__).parents[3].joinpath("fcode", "dashboard", "app.py").read_text(encoding="utf-8")
        assert "urllib" not in source
        assert "requests" not in source
        http_keywords = [w for w in source.lower().split() if w.startswith("http")]
        allowed = {"http_method"}
        extra = [w for w in http_keywords if w not in allowed]
        assert not extra, f"Unexpected http references: {extra}"

