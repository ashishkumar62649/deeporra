"""WP5 Step 4 metadata + FTS persist helpers.

Maps in-memory pipeline artifacts (ScanResult, ParsedFile list, CodeChunk list)
to canonical SQLite row dicts and runs FTS rebuild on the same connection so
SQLite metadata and FTS5 virtual tables share one real transaction.

Modules:
- `to_file_rows(scanned_files)` -> list of dicts for `SQLiteStore.insert_files`.
- `to_symbol_rows(parsed_files, file_id_map)` -> list of dicts for `SQLiteStore.insert_symbols`.
- `to_chunk_rows(chunks)` -> list of dicts for `SQLiteStore.insert_chunks`.
- `run_step4_persistence(scan_result, parsed_files, chunks, sqlite_store, fts_store, repo_path)` -> str repo_id

This module does NOT import Chroma, does NOT import graph-store, does NOT use
sqlite3 directly, and does NOT execute subprocess or network code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fcode.contracts.enums import HttpMethod, ParseStatus
from fcode.contracts.models import (
    CodeChunk,
    ParsedFile,
    ScanResult,
    ScannedFile,
)
from fcode.storage.fts_store import FTSStore
from fcode.storage.sqlite_store import SQLiteStore


_FILE_TYPE_TO_STR = {
    "source": "source",
    "test": "test",
    "config": "config",
    "doc": "doc",
}

_PARSE_STATUS_TO_STR = {
    ParseStatus.PARSED: "parsed",
    ParseStatus.ERROR: "error",
    ParseStatus.PENDING: "pending",
    ParseStatus.NOT_APPLICABLE: "not_applicable",
}

_SYMBOL_KIND_TO_STR = {
    "function": "function",
    "class": "class",
    "method": "method",
    "route": "route",
    "variable": "variable",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_type_str(value) -> str:
    raw = getattr(value, "value", value)
    return _FILE_TYPE_TO_STR.get(str(raw), "source")


def _parse_status_str(status: ParseStatus) -> str:
    return _PARSE_STATUS_TO_STR.get(status, "not_applicable")


def _symbol_type_str(value) -> str:
    raw = getattr(value, "value", value)
    return _SYMBOL_KIND_TO_STR.get(str(raw), "function")


def _confidence_str(value) -> str:
    raw = getattr(value, "value", value)
    return str(raw) if raw in ("EXTRACTED", "INFERRED", "AMBIGUOUS") else "EXTRACTED"


def _http_method_str(method: HttpMethod) -> str:
    return getattr(method, "value", str(method))


def _safe_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _json_safe(obj: Any) -> Any:
    """Convert dataclasses/enums to JSON-serializable primitives."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    raw_value = getattr(obj, "value", None)
    if raw_value is not None and isinstance(raw_value, (str, int, float, bool)):
        return raw_value
    return str(obj)


def _dump_metadata(meta: Any) -> Optional[str]:
    if meta is None or meta == {} or meta == {}:
        return None
    try:
        return json.dumps(_json_safe(meta), ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None


# ── Row projections ──────────────────────────────────────────────────────────


def to_file_rows(scanned_files: list[ScannedFile], parsed_files: list[ParsedFile] | None = None) -> list[dict]:
    parsed = {file.file_id: file for file in parsed_files or []}
    rows: list[dict] = []
    for sf in scanned_files:
        rows.append({
            "id": sf.file_id,
            "repo_id": None,  # filled by caller
            "path": sf.file_path,
            "absolute_path": sf.absolute_path or sf.file_path,
            "language": _safe_str(sf.language, default=""),
            "file_type": _file_type_str(sf.file_type),
            "size_bytes": int(sf.size_bytes or 0),
            "line_count": int(sf.line_count or 0),
            "content_hash": _safe_str(sf.content_hash, default=""),
            "has_secrets": 1 if getattr(sf, "has_secrets", False) else 0,
            "parse_status": _parse_status_str(parsed.get(sf.file_id).status if sf.file_id in parsed else sf.parse_status),
            "parse_error": (_safe_str(parsed[sf.file_id].parse_error)[:500]) if sf.file_id in parsed and parsed[sf.file_id].parse_error else None,
            "indexed_at": _utcnow(),
        })
    return rows


def _route_metadata(pf: ParsedFile) -> list[dict]:
    out: list[dict] = []
    for r in pf.routes:
        out.append({
            "route_id": _safe_str(r.route_id),
            "route_path": _safe_str(r.route_path),
            "method": _http_method_str(r.method),
            "handler_function": _safe_str(r.handler_function),
            "decorators": list(r.decorators) if r.decorators else [],
            "start_line": int(r.start_line or 0),
        })
    return out


def to_symbol_rows(
    parsed_files: list[ParsedFile],
    file_id_map: dict[tuple[str, str], str],
) -> list[dict]:
    rows: list[dict] = []
    for pf in parsed_files:
        key = (pf.file_id, pf.file_path)
        file_row_id = file_id_map.get(key, pf.file_id)
        route_meta = {m["route_id"]: m for m in _route_metadata(pf)}

        for sym in pf.symbols:
            sid = _safe_str(sym.symbol_id)
            raw_meta = sym.metadata or {}

            if sym.symbol_type.value == "route":
                rmeta = route_meta.get(sid, {})
                merged_meta = {**raw_meta, **rmeta}
            else:
                merged_meta = raw_meta

            rows.append({
                "id": sid,
                "repo_id": None,
                "file_id": file_row_id,
                "symbol_type": _symbol_type_str(sym.symbol_type),
                "name": _safe_str(sym.name),
                "qualified_name": _safe_str(sym.qualified_name),
                "start_line": int(sym.start_line or 0),
                "end_line": int(sym.end_line or 0),
                "signature": _safe_str(sym.signature, default="") or None,
                "docstring": _safe_str(sym.docstring, default="") or None,
                "parent_symbol_id": _safe_str(sym.parent_symbol_id, default="") or None,
                "metadata": _dump_metadata(merged_meta),
            })

        symbol_ids = {row["id"] for row in rows}
        for route in pf.routes:
            if route.route_id in symbol_ids:
                continue
            rows.append({
                "id": route.route_id,
                "repo_id": None,
                "file_id": file_row_id,
                "symbol_type": "route",
                "name": route.handler_function,
                "qualified_name": route.handler_function,
                "start_line": route.start_line,
                "end_line": route.start_line,
                "signature": None,
                "docstring": None,
                "parent_symbol_id": None,
                "metadata": _dump_metadata({
                    "route_path": route.route_path,
                    "method": _http_method_str(route.method),
                    "decorators": list(route.decorators),
                }),
            })
    return rows


def to_chunk_rows(chunks: list[CodeChunk]) -> list[dict]:
    rows: list[dict] = []
    for c in chunks:
        ct = getattr(c.chunk_type, "value", c.chunk_type)
        rows.append({
            "id": _safe_str(c.chunk_id),
            "repo_id": None,
            "file_id": _safe_str(c.file_id),
            "symbol_id": _safe_str(c.symbol_id, default="") or None,
            "chunk_type": str(ct),
            "content": str(c.content),
            "start_line": int(c.start_line or 0),
            "end_line": int(c.end_line or 0),
            "content_hash": _safe_str(c.content_hash),
            "language": _safe_str(c.language, default="") or None,
            "symbol_name": _safe_str(c.symbol_name, default=""),
            "file_path": _safe_str(c.file_path),
            "metadata": _dump_metadata(c.metadata),
        })
    return rows


# ── Run-Step-4 persistence ──────────────────────────────────────────────────


def run_step4_persistence(
    scan_result: ScanResult,
    parsed_files: list[ParsedFile],
    chunks: list[CodeChunk],
    sqlite_store: SQLiteStore,
    fts_store: FTSStore,
    repo_path: str,
    content_hash: Optional[str] = None,
    *,
    warning_count: int = 0,
    error_count: int = 0,
    embedding_model: Optional[str] = None,
) -> dict:
    """Perform the Step 4 stage-write:

    1. schema initialize (idempotent)
    2. repository row (new path; if path already exists -> controlled conflict)
    3. index_status insertion
    4. files
    5. symbols (one per ParsedSymbol including ROUTE ones)
    6. chunks
    7. FTS rebuild (chunks_fts and symbols_fts via INSERT ... 'rebuild')

    SQLite metadata writes and FTS rebuild share one `sqlite3.Connection`.

    Returns a dict with keys: `repo_id`, `file_count`, `symbol_count`,
    `chunk_count`, `fts_count`, `path`, `rebuild`.

    Raises `RuntimeError` if the path is already taken (so caller can mark ERROR
    without silently mixing and matches).
    """

    conn = sqlite_store.conn

    # 1. Initialize the schema (idempotent — only applies once per DB).
    sqlite_store.initialize_schema()

    # Conflict detection: refuse silent collision with an existing active
    # repository row at the same canonical path. Step 5 owns coordinated
    # replacement; Step 4 stays safe.
    existing_repo_id = sqlite_store.find_repository(repo_path)
    if existing_repo_id is not None:
        raise AlreadyIndexedRepositoryError(repo_path, existing_repo_id)

    # ── Begin transaction for content writes ────────────────────────────────
    sqlite_store.begin_transaction()
    try:
        # 2. repositories row + initial index_status row.
        repo_id = sqlite_store.create_repository_and_status(repo_path, content_hash=content_hash)

        # 3. file rows.
        file_rows = to_file_rows(list(scan_result.files), parsed_files)
        for row in file_rows:
            row["repo_id"] = repo_id
        if file_rows:
            sqlite_store.insert_files(repo_id, file_rows)

        # 4. symbol rows.
        scanned_lookup = {(sf.file_id, sf.file_path): sf.file_id for sf in scan_result.files}
        parsed_lookup = dict(scanned_lookup)
        symbol_rows = to_symbol_rows(parsed_files, parsed_lookup)
        for row in symbol_rows:
            row["repo_id"] = repo_id
        if symbol_rows:
            sqlite_store.insert_symbols(repo_id, symbol_rows)

        # 5. chunk rows.
        chunk_rows = to_chunk_rows(chunks)
        for row in chunk_rows:
            row["repo_id"] = repo_id
        if chunk_rows:
            sqlite_store.insert_chunks(repo_id, chunk_rows)

        fts_avail = fts_store.check_availability(conn)
        if fts_avail:
            fts_store.drop_tables(conn)
            fts_store.create_tables(conn)
            fts_store.rebuild_all(conn)

        file_count = sqlite_store.count_files(repo_id)
        symbol_count = sqlite_store.count_symbols(repo_id)
        chunk_count = sqlite_store.count_chunks(repo_id)
        fts_count = fts_store.count_chunks_fts(conn) if fts_avail else 0
        setup_status_after_step4(
            sqlite_store,
            repo_id,
            counts={
                "total_files": file_count,
                "indexed_files": file_count,
                "total_symbols": symbol_count,
                "total_chunks": chunk_count,
            },
            warning_count=warning_count,
            error_count=error_count,
            embedding_model=embedding_model,
            active_search_mode="fts5" if fts_avail else "like_fallback",
        )
        sqlite_store.commit_transaction()
    except Exception:
        sqlite_store.rollback_transaction()
        raise

    # ── FTS rebuild after content commit ────────────────────────────────────
    return {
        "repo_id": repo_id,
        "file_count": file_count,
        "symbol_count": symbol_count,
        "chunk_count": chunk_count,
        "fts_count": fts_count,
        "path": repo_path,
        "rebuild": fts_avail,
        "fts_available": fts_avail,
    }


class AlreadyIndexedRepositoryError(RuntimeError):
    """Raised when a Step 4 attempt targets a path whose repository row already exists."""

    def __init__(self, path: str, existing_repo_id: str):
        self.path = path
        self.existing_repo_id = existing_repo_id
        super().__init__(
            f"Repository row already exists for path"
        )


def setup_status_after_step4(
    sqlite_store: SQLiteStore,
    repo_id: str,
    counts: dict[str, int],
    warning_count: int = 0,
    error_count: int = 0,
    embedding_model: Optional[str] = None,
    active_search_mode: str = "fts5",
) -> None:
    """Update index_status row to reflect Step 4 STORING state without promotion.

    Does not mark `complete`. Does not delete any prior data.
    """
    sqlite_store.update_index_status(
        repo_id,
        status="storing",
        total_files=counts.get("total_files", 0),
        indexed_files=counts.get("indexed_files", 0),
        total_symbols=counts.get("total_symbols", 0),
        total_chunks=counts.get("total_chunks", 0),
        warning_count=warning_count,
        error_count=error_count,
        embedding_model=embedding_model,
        active_search_mode=active_search_mode,
    )
