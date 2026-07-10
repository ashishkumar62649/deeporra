"""Graph storage — code_nodes and code_edges persistence."""

import json
import sqlite3
from typing import Any, Optional

from fcode.contracts.interfaces import GraphStoreProtocol


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


class GraphStore:
    """Persistence for code graph nodes and edges.

    Uses a caller-provided SQLite connection. Never opens its own transaction.
    """

    def store_graph(self, nodes: list[dict], edges: list[dict]) -> None:
        pass

    def reset(self) -> None:
        pass

    # ── Node operations ─────────────────────────────────────────────────────

    def insert_nodes(
        self, conn: sqlite3.Connection, repo_id: str, nodes: list[dict]
    ) -> None:
        for n in nodes:
            metadata_str = _json_dumps(n["metadata"]) if n.get("metadata") else None
            conn.execute(
                """INSERT INTO code_nodes
                   (id, repo_id, node_id, label, node_type,
                    source_file, source_location, confidence, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    n["id"],
                    repo_id,
                    n["node_id"],
                    n["label"],
                    n["node_type"],
                    n.get("source_file", ""),
                    n.get("source_location"),
                    n.get("confidence", "EXTRACTED"),
                    metadata_str,
                ),
            )

    def insert_edges(
        self, conn: sqlite3.Connection, repo_id: str, edges: list[dict]
    ) -> None:
        for e in edges:
            metadata_str = _json_dumps(e["metadata"]) if e.get("metadata") else None
            conn.execute(
                """INSERT INTO code_edges
                   (id, repo_id, source_node_id, target_node_id,
                    relation, confidence, source_file, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["id"],
                    repo_id,
                    e["source_node_id"],
                    e["target_node_id"],
                    e["relation"],
                    e.get("confidence", "EXTRACTED"),
                    e.get("source_file"),
                    metadata_str,
                ),
            )

    # ── Count operations ────────────────────────────────────────────────────

    def count_nodes(self, conn: sqlite3.Connection, repo_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_nodes WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def count_edges(self, conn: sqlite3.Connection, repo_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_edges WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Read operations ─────────────────────────────────────────────────────

    def get_nodes(
        self, conn: sqlite3.Connection, repo_id: str
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM code_nodes WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges(
        self, conn: sqlite3.Connection, repo_id: str
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM code_edges WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nodes_by_type(
        self, conn: sqlite3.Connection, repo_id: str, node_type: str
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM code_nodes WHERE repo_id = ? AND node_type = ?",
            (repo_id, node_type),
        ).fetchall()
        return [dict(r) for r in rows]
