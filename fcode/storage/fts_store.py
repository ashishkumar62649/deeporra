"""FTS5 keyword search — external-content FTS5 tables and LIKE fallback."""

import sqlite3
from typing import Any, Optional

from fcode.contracts.interfaces import FTSStoreProtocol
from fcode.contracts.models import CodeChunk


FTS5_CHUNKS_DDL = """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    symbol_name,
    file_path,
    content='chunks',
    content_rowid='rowid'
)"""

FTS5_SYMBOLS_DDL = """CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name,
    qualified_name,
    content='symbols',
    content_rowid='rowid'
)"""


class FTSStore:
    """FTS5 keyword search with LIKE fallback.

    Uses a caller-provided SQLite connection for all operations.
    Does not open its own transaction.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self._conn = conn

    def rebuild(self, chunks: list[CodeChunk]) -> None:
        conn = self._require_conn()
        self.drop_tables(conn)
        if not self.check_availability(conn):
            return
        self.create_tables(conn)
        self.rebuild_all(conn)

    def reset(self) -> None:
        conn = self._require_conn()
        self.drop_tables(conn)

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("FTSStore not connected. Set ._conn or pass conn to __init__.")
        return self._conn

    # ── Availability detection ──────────────────────────────────────────────

    @staticmethod
    def check_availability(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT * FROM pragma_compile_options WHERE compile_options LIKE 'ENABLE_FTS5'")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("CREATE VIRTUAL TABLE _fcode_fts_test USING fts5(content)")
            conn.execute("DROP TABLE _fcode_fts_test")
            return True
        except sqlite3.OperationalError:
            return False
        except sqlite3.DatabaseError:
            return False

    # ── Table management ────────────────────────────────────────────────────

    def create_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(FTS5_CHUNKS_DDL)
        conn.execute(FTS5_SYMBOLS_DDL)

    def drop_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute("DROP TABLE IF EXISTS symbols_fts")

    # ── Rebuild ─────────────────────────────────────────────────────────────

    def rebuild_all(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild')")

    # ── Count operations ────────────────────────────────────────────────────

    def count_chunks_fts(self, conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM chunks_fts").fetchone()
            return row["cnt"] if row else 0
        except sqlite3.OperationalError:
            return 0

    def count_symbols_fts(self, conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM symbols_fts").fetchone()
            return row["cnt"] if row else 0
        except sqlite3.OperationalError:
            return 0

    # ── FTS5 search ─────────────────────────────────────────────────────────

    def search_chunks(
        self, conn: sqlite3.Connection, query: str, repo_id: str, limit: int = 20
    ) -> list[dict]:
        try:
            rows = conn.execute(
                """SELECT c.id, c.repo_id, c.file_id, c.symbol_id, c.chunk_type,
                           c.content, c.start_line, c.end_line, c.language,
                           c.symbol_name, f.path AS file_path,
                           chunks_fts.rank
                    FROM chunks_fts
                    JOIN chunks c ON c.rowid = chunks_fts.rowid
                    JOIN files f ON f.id = c.file_id
                    WHERE chunks_fts MATCH ? AND c.repo_id = ?
                    ORDER BY chunks_fts.rank
                    LIMIT ?""",
                (query, repo_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return self.search_chunks_like(conn, query, repo_id, limit)

    def search_symbols(
        self, conn: sqlite3.Connection, query: str, repo_id: str, limit: int = 20
    ) -> list[dict]:
        try:
            rows = conn.execute(
                """SELECT s.id, s.repo_id, s.file_id, s.symbol_type, s.name,
                           s.qualified_name, s.start_line, s.end_line,
                           s.signature, f.path AS file_path,
                           symbols_fts.rank
                    FROM symbols_fts
                    JOIN symbols s ON s.rowid = symbols_fts.rowid
                    JOIN files f ON f.id = s.file_id
                    WHERE symbols_fts MATCH ? AND s.repo_id = ?
                    ORDER BY symbols_fts.rank
                    LIMIT ?""",
                (query, repo_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return self.search_symbols_like(conn, query, repo_id, limit)

    # ── LIKE fallback search ────────────────────────────────────────────────

    @staticmethod
    def _like_pattern(query: str) -> str:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def search_chunks_like(
        self, conn: sqlite3.Connection, query: str, repo_id: str, limit: int = 20
    ) -> list[dict]:
        pattern = self._like_pattern(query)
        rows = conn.execute(
            """SELECT c.*, f.path AS file_path
                FROM chunks c
                JOIN files f ON f.id = c.file_id
                WHERE c.repo_id = ? AND c.content LIKE ? ESCAPE '\\'
                LIMIT ?""",
            (repo_id, pattern, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_symbols_like(
        self, conn: sqlite3.Connection, query: str, repo_id: str, limit: int = 20
    ) -> list[dict]:
        pattern = self._like_pattern(query)
        rows = conn.execute(
            """SELECT s.*, f.path AS file_path
                FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.repo_id = ? AND s.name LIKE ? ESCAPE '\\'
                LIMIT ?""",
            (repo_id, pattern, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_chunks_fts_only(
        self, conn: sqlite3.Connection, query: str, repo_id: str, limit: int = 20
    ) -> list[dict]:
        try:
            rows = conn.execute(
                """SELECT c.id, c.repo_id, c.file_id, c.symbol_id, c.chunk_type,
                           c.content, c.start_line, c.end_line, c.language,
                           c.symbol_name, f.path AS file_path,
                           chunks_fts.rank
                    FROM chunks_fts
                    JOIN chunks c ON c.rowid = chunks_fts.rowid
                    JOIN files f ON f.id = c.file_id
                    WHERE chunks_fts MATCH ? AND c.repo_id = ?
                    ORDER BY chunks_fts.rank
                    LIMIT ?""",
                (query, repo_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
