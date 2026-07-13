"""FastMCP-based read-only stdio server for F Code.

Each tool call creates a short-lived QueryService instance.
No shared state, no network listener, no writes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

from mcp.server.fastmcp import FastMCP

from fcode.querying import (
    CodeSearchResult,
    ImpactAnalysis,
    QueryService,
    QueryValidationError,
    RelatedNode,
    RepositoryNotIndexedError,
    RepositorySummary,
    RouteRecord,
    SymbolRecord,
)

SERVER_NAME = "fcode-mcp"
SERVER_VERSION = "0.1.0"
SERVER_INSTRUCTIONS = (
    "Read-only repository intelligence for F Code. "
    "All tools require a repository_root that has been indexed by F Code. "
    "Results are JSON-serializable dicts. No files are modified."
)
MAX_LIMIT = 500


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _to_serializable(obj: Any) -> Any:
    if isinstance(obj, (CodeSearchResult, SymbolRecord, RouteRecord, RelatedNode, ImpactAnalysis, RepositorySummary)):
        return asdict(obj)
    if isinstance(obj, list):
        return [_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    return obj


def _validate_root(root: str) -> None:
    if not root or not root.strip():
        raise QueryValidationError("repository_root must not be blank.")


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or limit < 1:
        raise QueryValidationError("limit must be a positive integer.")
    if limit > MAX_LIMIT:
        raise QueryValidationError(f"limit must not exceed {MAX_LIMIT}.")


def _service_for(root: str) -> QueryService:
    _validate_root(root)
    return QueryService(root)


def _safe_json(result: Any) -> str:
    serializable = _to_serializable(result)
    return json.dumps(serializable, default=_json_default, ensure_ascii=False)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        debug=False,
        log_level="ERROR",
    )

    # ── Tool 1: repository_summary ────────────────────────────────────

    @mcp.tool()
    def repository_summary(repository_root: str) -> str:
        """Return summary statistics for an indexed repository."""
        qs = _service_for(repository_root)
        result = qs.get_repository_summary()
        return _safe_json(result)

    # ── Tool 2: search_code ───────────────────────────────────────────

    @mcp.tool()
    def search_code(
        repository_root: str,
        query: str,
        mode: str = "hybrid",
        limit: int = 10,
    ) -> str:
        """Search code chunks by text, semantic, or hybrid mode."""
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        results = qs.search_code(query=query, limit=limit, mode=mode)
        return _safe_json(results)

    # ── Tool 3: hybrid_search ────────────────────────────────────────

    @mcp.tool()
    def hybrid_search(
        repository_root: str,
        query: str,
        limit: int = 10,
    ) -> str:
        """Search code using hybrid (text + semantic) ranking."""
        _validate_root(repository_root)
        if not query or not query.strip():
            raise QueryValidationError("query must not be blank.")
        _validate_limit(limit)
        qs = QueryService(repository_root)
        results = qs.search_code(query=query, limit=limit, mode="hybrid")
        return _safe_json(results)

    # ── Tool 4: find_symbols ─────────────────────────────────────────

    @mcp.tool()
    def find_symbols(
        repository_root: str,
        query: str,
        exact: bool = False,
        limit: int = 20,
    ) -> str:
        """Find symbols (functions, classes, methods) matching a name query."""
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        results = qs.find_symbols(query=query, exact=exact, limit=limit)
        return _safe_json(results)

    # ── Tool 5: find_routes ─────────────────────────────────────────

    @mcp.tool()
    def find_routes(
        repository_root: str,
        method: str = "",
        path_query: str = "",
        handler_query: str = "",
        limit: int = 50,
    ) -> str:
        """Find HTTP route definitions matching method, path, or handler."""
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        results = qs.find_routes(
            method=method or None,
            path_query=path_query or None,
            handler_query=handler_query or None,
            limit=limit,
        )
        return _safe_json(results)

    # ── Tool 6: get_related_code ─────────────────────────────────────

    @mcp.tool()
    def get_related_code(
        repository_root: str,
        semantic_key: str,
        direction: str = "both",
        edge_types: str = "",
        depth: int = 1,
        limit: int = 100,
    ) -> str:
        """Find related code nodes through graph edges (one-hop)."""
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        et: list[str] | None = None
        if edge_types:
            et = [t.strip() for t in edge_types.split(",") if t.strip()]
        results = qs.get_related(
            semantic_key=semantic_key,
            direction=direction,
            edge_types=et,
            depth=depth,
            limit=limit,
        )
        return _safe_json(results)

    # ── Tool 7: analyze_change_impact ────────────────────────────────

    @mcp.tool()
    def analyze_change_impact(
        repository_root: str,
        semantic_key: str,
        limit: int = 100,
    ) -> str:
        """Analyze first-order change impact for a symbol.

        This provides direct, first-order impact only — not complete transitive analysis.
        """
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        result = qs.analyze_change_impact(semantic_key=semantic_key, limit=limit)
        return _safe_json(result)

    # ── Tool 8: find_existing_implementation ─────────────────────────

    @mcp.tool()
    def find_existing_implementation(
        repository_root: str,
        query: str,
        limit: int = 10,
    ) -> str:
        """Search for existing code that may match a description.

        Composes search_code and find_symbols to return candidate locations.
        Results are candidates, not proof of equivalence.
        """
        _validate_root(repository_root)
        _validate_limit(limit)
        qs = QueryService(repository_root)
        code_results = qs.search_code(query=query, limit=limit, mode="text")
        symbol_results = qs.find_symbols(query=query, exact=False, limit=limit)
        return _safe_json({
            "code_results": code_results,
            "symbol_results": symbol_results,
        })

    return mcp
