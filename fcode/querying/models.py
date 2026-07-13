"""Typed result models for the read-only query service.

All models are JSON-serializable dataclasses with stable field names.
No raw SQLite rows or Chroma objects exposed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


def _default_serializer(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def to_json(obj: Any) -> str:
    """Serialize a dataclass (or list of dataclasses) to JSON."""
    return json.dumps(obj, default=_default_serializer, ensure_ascii=False, indent=2)


# ── Errors ──────────────────────────────────────────────────────────────


class RepositoryNotIndexedError(LookupError):
    """Raised when no valid active index exists for the repository."""


class QueryValidationError(ValueError):
    """Raised for invalid query parameters."""


# ── Repository summary ──────────────────────────────────────────────────


@dataclass(frozen=True)
class RepositorySummary:
    repository_root: str
    active_generation_id: str
    index_status: str
    indexed_at: Optional[str]
    file_count: int
    parsed_count: int
    not_applicable_count: int
    error_count: int
    symbol_count: int
    import_count: int
    route_count: int
    test_count: int
    chunk_count: int
    graph_node_count: int
    graph_edge_count: int
    warning_count: int
    fatal_error_count: int


# ── Code search results ────────────────────────────────────────────────


@dataclass(frozen=True)
class CodeSearchResult:
    chunk_id: str
    source_path: str
    start_line: int
    end_line: int
    chunk_kind: str
    owner_semantic_key: Optional[str]
    display_text: str
    text_score: Optional[float]
    semantic_score: Optional[float]
    combined_score: float
    match_source: str  # "text", "semantic", or "both"


# ── Symbol lookup ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SymbolRecord:
    semantic_key: str
    kind: str
    qualified_name: str
    source_path: str
    start_line: int
    end_line: int
    parent_semantic_key: Optional[str]


# ── Route lookup ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class RouteRecord:
    http_method: str
    route_path: str
    handler_semantic_key: str
    handler_name: str
    source_path: str
    decorator_line: int
    handler_start_line: int
    handler_end_line: int


# ── Related-code lookup ────────────────────────────────────────────────


@dataclass(frozen=True)
class RelatedNode:
    center_identity: str
    related_node_identity: str
    node_kind: str
    qualified_name: str
    source_path: str
    relationship_type: str
    direction: str  # "outgoing" or "incoming"
    qualifier: Optional[str]


# ── Impact analysis ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImpactAnalysis:
    target_semantic_key: str
    target_kind: str
    target_qualified_name: str
    target_source_path: str
    analysis_type: str  # "first_order"
    direct_callers: list[SymbolRecord] = field(default_factory=list)
    direct_callees: list[SymbolRecord] = field(default_factory=list)
    containing_file: Optional[str] = None
    containing_class: Optional[str] = None
    import_relationships: list[RelatedNode] = field(default_factory=list)
    route_relationships: list[RelatedNode] = field(default_factory=list)
    related_tests: list[SymbolRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
