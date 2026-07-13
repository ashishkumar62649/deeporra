"""Read-only wrapper layer between the Streamlit UI and QueryService.

All functions in this module return plain-data results or error strings.
No Streamlit dependency.  No side effects.
"""

from __future__ import annotations

from fcode.querying import (
    QueryService,
    QueryValidationError,
    RepositoryNotIndexedError,
    RepositorySummary,
)


def safe_summary(qs: QueryService) -> RepositorySummary | str | None:
    try:
        return qs.get_repository_summary()
    except RepositoryNotIndexedError:
        return "Repository is not indexed. Run `fcode index` first."
    except Exception as exc:
        return f"Query error: {exc}"


def safe_search(
    qs: QueryService, query: str, limit: int, mode: str
) -> list | str:
    try:
        return qs.search_code(query, limit=limit, mode=mode)
    except QueryValidationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Search error: {exc}"


def safe_symbols(
    qs: QueryService, query: str, limit: int, exact: bool
) -> list | str:
    try:
        return qs.find_symbols(query, limit=limit, exact=exact)
    except QueryValidationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Symbol lookup error: {exc}"


def safe_routes(
    qs: QueryService,
    method: str | None,
    path_q: str | None,
    handler_q: str | None,
    limit: int,
) -> list | str:
    try:
        return qs.find_routes(
            method=method or None,
            path_query=path_q or None,
            handler_query=handler_q or None,
            limit=limit,
        )
    except Exception as exc:
        return f"Route lookup error: {exc}"


def safe_related(
    qs: QueryService,
    semantic_key: str,
    direction: str,
    edge_types: list[str] | None,
    limit: int,
) -> list | str:
    try:
        return qs.get_related(
            semantic_key=semantic_key,
            direction=direction,
            edge_types=edge_types or None,
            depth=1,
            limit=limit,
        )
    except QueryValidationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Related-code error: {exc}"


def safe_impact(
    qs: QueryService, semantic_key: str, limit: int
) -> dict | str:
    try:
        impact = qs.analyze_change_impact(semantic_key, limit=limit)
        return {
            "target": impact.target_qualified_name,
            "kind": impact.target_kind,
            "source_path": impact.target_source_path,
            "analysis_type": impact.analysis_type,
            "direct_callers": impact.direct_callers,
            "direct_callees": impact.direct_callees,
            "containing_file": impact.containing_file,
            "containing_class": impact.containing_class,
            "import_relationships": impact.import_relationships,
            "route_relationships": impact.route_relationships,
            "related_tests": impact.related_tests,
            "warnings": impact.warnings,
        }
    except QueryValidationError as exc:
        return str(exc)
    except Exception as exc:
        return f"Impact analysis error: {exc}"
