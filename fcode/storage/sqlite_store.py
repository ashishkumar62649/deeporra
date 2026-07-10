"""SQLite storage — schema, repositories, files, symbols, chunks, status."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from fcode.contracts.interfaces import SQLiteStoreProtocol
from fcode.contracts.models import IndexRunResult, IndexStatusRecord
from fcode.storage.migrations.v001_initial import SCHEMA_VERSION, apply as apply_migration


MAX_ERROR_LENGTH = 500


def _sanitize_error(msg: str) -> str:
    return msg[:MAX_ERROR_LENGTH]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _row_to_dict(row: sqlite3.Row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


class SQLiteStore:
    """SQLite persistence for F Code metadata, symbols, chunks, and status."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteStore not connected. Call connect() first.")
        return self._conn

    def connect(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        schema_ver = self._get_schema_version()
        if schema_ver is None:
            apply_migration(self._conn)
            self._conn.commit()
        elif schema_ver == SCHEMA_VERSION:
            pass
        elif schema_ver > SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema version {schema_ver}. "
                f"This version supports schema version {SCHEMA_VERSION}. "
                "Downgrade is not supported."
            )
        else:
            raise ValueError(
                f"Unsupported schema version {schema_ver}. "
                f"Expected version {SCHEMA_VERSION}. "
                "Migration is not supported."
            )

    def _get_schema_version(self) -> Optional[int]:
        try:
            row = self._conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            return row["version"] if row else None
        except sqlite3.OperationalError:
            return None

    def get_schema_version(self) -> int:
        return SCHEMA_VERSION

    # ── Transaction management ──────────────────────────────────────────────

    def begin_transaction(self) -> None:
        self._conn.execute("BEGIN")

    def commit_transaction(self) -> None:
        self._conn.commit()

    def rollback_transaction(self) -> None:
        self._conn.rollback()

    # ── Repository operations ───────────────────────────────────────────────

    def find_repository(self, path: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT id FROM repositories WHERE path = ?", (path,)
        ).fetchone()
        return row["id"] if row else None

    def create_repository_and_status(
        self, path: str, content_hash: Optional[str] = None
    ) -> str:
        import uuid
        repo_id = str(uuid.uuid4())
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO repositories (id, path, content_hash, indexed_at) VALUES (?, ?, ?, ?)",
            (repo_id, path, content_hash, now),
        )
        self._conn.execute(
            "INSERT INTO index_status (repo_id, status, started_at) VALUES (?, 'pending', ?)",
            (repo_id, now),
        )
        return repo_id

    def read_index_status(self, repo_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM index_status WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return _row_to_dict(row)

    def upsert_repository(
        self, repo_id: str, path: str, content_hash: Optional[str] = None
    ) -> None:
        now = _utcnow()
        self._conn.execute(
            "UPDATE repositories SET path = ?, content_hash = ?, indexed_at = ? WHERE id = ?",
            (path, content_hash, now, repo_id),
        )

    def delete_repository_content(self, repo_id: str) -> None:
        self._conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM symbols WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM code_nodes WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM code_edges WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM repo_reports WHERE repo_id = ?", (repo_id,))
        self._conn.execute("DELETE FROM tool_call_logs WHERE repo_id = ?", (repo_id,))

    # ── File operations ─────────────────────────────────────────────────────

    def insert_files(self, repo_id: str, files: list[dict]) -> None:
        for f in files:
            self._conn.execute(
                """INSERT INTO files
                   (id, repo_id, path, absolute_path, language, file_type,
                    size_bytes, line_count, content_hash, has_secrets,
                    parse_status, parse_error, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f["id"],
                    repo_id,
                    f.get("path", ""),
                    f.get("absolute_path", ""),
                    f.get("language"),
                    f.get("file_type"),
                    f.get("size_bytes"),
                    f.get("line_count"),
                    f.get("content_hash"),
                    f.get("has_secrets", 0),
                    f.get("parse_status", "not_applicable"),
                    _sanitize_error(f["parse_error"]) if f.get("parse_error") else None,
                    f.get("indexed_at") or _utcnow(),
                ),
            )

    # ── Symbol operations ───────────────────────────────────────────────────

    def insert_symbols(self, repo_id: str, symbols: list[dict]) -> None:
        for s in symbols:
            metadata_str = _json_dumps(s["metadata"]) if s.get("metadata") else None
            self._conn.execute(
                """INSERT INTO symbols
                   (id, repo_id, file_id, symbol_type, name, qualified_name,
                    start_line, end_line, signature, docstring,
                    parent_symbol_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["id"],
                    repo_id,
                    s["file_id"],
                    s["symbol_type"],
                    s["name"],
                    s.get("qualified_name"),
                    s.get("start_line"),
                    s.get("end_line"),
                    s.get("signature"),
                    s.get("docstring"),
                    s.get("parent_symbol_id"),
                    metadata_str,
                ),
            )

    # ── Chunk operations ────────────────────────────────────────────────────

    def insert_chunks(self, repo_id: str, chunks: list[dict]) -> None:
        for c in chunks:
            metadata_str = _json_dumps(c["metadata"]) if c.get("metadata") else None
            self._conn.execute(
                """INSERT INTO chunks
                   (id, repo_id, file_id, symbol_id, chunk_type, content,
                    start_line, end_line, content_hash, language,
                    symbol_name, file_path, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c["id"],
                    repo_id,
                    c["file_id"],
                    c.get("symbol_id"),
                    c["chunk_type"],
                    c["content"],
                    c.get("start_line"),
                    c.get("end_line"),
                    c.get("content_hash"),
                    c.get("language"),
                    c.get("symbol_name"),
                    c["file_path"],
                    metadata_str,
                ),
            )

    # ── Index status operations ─────────────────────────────────────────────

    def update_index_status(self, repo_id: str, **kwargs: Any) -> None:
        allowed = {
            "status", "total_files", "indexed_files", "total_symbols",
            "total_chunks", "total_graph_nodes", "total_edges",
            "total_vectors", "warning_count", "error_count",
            "embedding_model", "active_search_mode",
            "started_at", "completed_at", "error_message",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        if "error_message" in updates:
            updates["error_message"] = _sanitize_error(updates["error_message"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [repo_id]
        self._conn.execute(
            f"UPDATE index_status SET {set_clause} WHERE repo_id = ?", values
        )

    # ── Count operations ────────────────────────────────────────────────────

    def count_files(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM files WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_symbols(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM symbols WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_chunks(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_graph_nodes(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_nodes WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_graph_edges(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_edges WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_vectors(self, repo_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(total_vectors), 0) AS cnt FROM index_status WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def cleanup_failed_replacement(
        self,
        repo_id: str,
        error_message: str,
        warning_count: int = 0,
        error_count: int = 0,
    ) -> None:
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM symbols WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM code_nodes WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM code_edges WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM repo_reports WHERE repo_id = ?", (repo_id,))
            self._conn.execute("DELETE FROM tool_call_logs WHERE repo_id = ?", (repo_id,))
            now = _utcnow()
            self._conn.execute(
                """UPDATE index_status SET
                    status = 'error',
                    completed_at = ?,
                    error_message = ?,
                    warning_count = ?,
                    error_count = ?
                   WHERE repo_id = ?""",
                (now, _sanitize_error(error_message), warning_count, error_count, repo_id),
            )
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    # ── SQLiteStoreProtocol conformance ─────────────────────────────────────

    def store_index_run(self, result: IndexRunResult) -> None:
        repo_id = self.find_repository(".")
        if repo_id:
            self.update_index_status(
                repo_id,
                status=result.state.value if hasattr(result.state, "value") else str(result.state),
            )

    def get_index_status(self) -> Optional[IndexStatusRecord]:
        row = self._conn.execute(
            "SELECT * FROM index_status LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        from fcode.contracts.enums import IndexState, IndexPhase
        from fcode.contracts.models import IndexCounts
        d = dict(row)
        counts = IndexCounts(
            scanned=d.get("total_files", 0) or 0,
            parsed=d.get("total_symbols", 0) or 0,
            graph_nodes=d.get("total_graph_nodes", 0) or 0,
            graph_edges=d.get("total_edges", 0) or 0,
            chunks=d.get("total_chunks", 0) or 0,
            embedded=d.get("total_vectors", 0) or 0,
        )
        raw_status = d.get("status", "pending")
        try:
            state = IndexState(raw_status)
        except ValueError:
            state = IndexState.PENDING
        return IndexStatusRecord(
            state=state,
            counts=counts,
            total_vectors=d.get("total_vectors", 0) or 0,
            error_count=d.get("error_count", 0) or 0,
        )

    def store_file_records(self, records: list[dict]) -> None:
        if not records:
            return
        repo_id = records[0].get("repo_id")
        if repo_id:
            self.insert_files(repo_id, records)

    def store_graph(self, nodes: list[dict], edges: list[dict]) -> None:
        if nodes:
            repo_id = nodes[0].get("repo_id", "")
            for n in nodes:
                self._conn.execute(
                    """INSERT INTO code_nodes
                       (id, repo_id, node_id, label, node_type,
                        source_file, source_location, confidence, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        n["id"],
                        n.get("repo_id", repo_id),
                        n["node_id"],
                        n["label"],
                        n["node_type"],
                        n.get("source_file", ""),
                        n.get("source_location"),
                        n.get("confidence", "EXTRACTED"),
                        _json_dumps(n["metadata"]) if n.get("metadata") else None,
                    ),
                )
        if edges:
            repo_id = edges[0].get("repo_id", "")
            for e in edges:
                self._conn.execute(
                    """INSERT INTO code_edges
                       (id, repo_id, source_node_id, target_node_id,
                        relation, confidence, source_file, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        e["id"],
                        e.get("repo_id", repo_id),
                        e["source_node_id"],
                        e["target_node_id"],
                        e["relation"],
                        e.get("confidence", "EXTRACTED"),
                        e.get("source_file"),
                        _json_dumps(e["metadata"]) if e.get("metadata") else None,
                    ),
                )

    def store_chunks(self, chunks: list[dict]) -> None:
        if chunks:
            repo_id = chunks[0].get("repo_id", "")
            self.insert_chunks(repo_id, chunks)

    def reset(self) -> None:
        repo_id = self.find_repository(".")
        if repo_id:
            self.delete_repository_content(repo_id)
