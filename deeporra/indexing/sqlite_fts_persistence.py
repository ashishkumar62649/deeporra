"""WP5 Step 4 metadata + FTS persistence.

Maps in-memory pipeline artifacts (ScanResult, ParsedFile list, CodeChunk
list) into one transactional SQLite write: metadata rows (via `SQLiteStore`
and its `to_file_rows`/`to_symbol_rows`/`to_chunk_rows` projections) and the
FTS5 rebuild (via `FTSStore`) share a single `sqlite3.Connection`.

This module does NOT import Chroma, does NOT import graph-store, does NOT use
sqlite3 directly, and does NOT execute subprocess or network code.
"""

from __future__ import annotations

from typing import Optional

from deeporra.contracts.models import CodeChunk, ParsedFile, ScanResult
from deeporra.storage.fts_store import FTSStore
from deeporra.storage.sqlite_store import SQLiteStore, to_chunk_rows, to_file_rows, to_symbol_rows


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
            "Repository row already exists for path"
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
