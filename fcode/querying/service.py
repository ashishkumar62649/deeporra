"""Read-only query service for an already-indexed F Code repository.

Provides one reusable internal API that MCP, the dashboard, and CLI commands
can use to search and inspect an already indexed repository.

Never creates a new index, activates a generation, writes to SQLite or Chroma,
modifies repository source files, or creates .fcode when it does not exist.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from fcode.contracts import (
    ChunkType,
    GraphRelation,
    IndexCounts,
)
from fcode.embeddings.encoder import (
    EXPECTED_DIMENSION,
    EmbeddingEncoder,
    EmbeddingEncoderError,
    EmbeddingInput,
    EmbeddingMetadata,
)
from fcode.indexing.full_rebuild import FullRebuildCoordinator, FullRebuildError
from fcode.storage.chroma_store import ChromaStore, COLLECTION_NAME
from fcode.storage.fts_store import FTSStore
from fcode.storage.graph_store import GraphStore
from fcode.storage.sqlite_store import SQLiteStore

from fcode.querying.models import (
    CodeSearchResult,
    ImpactAnalysis,
    QueryValidationError,
    RelatedNode,
    RepositoryNotIndexedError,
    RepositorySummary,
    RouteRecord,
    SymbolRecord,
)

MAX_LIMIT = 500
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_SYMBOL_LIMIT = 20
DEFAULT_ROUTE_LIMIT = 50
DEFAULT_RELATED_LIMIT = 100
DEFAULT_IMPACT_LIMIT = 100
SEMANTIC_SEARCH_LIMIT = 50


class QueryService:
    """Read-only query service for a single F Code indexed repository.

    Resolves the active generation once per operation through a short-lived
    SQLite/Chroma context. All connections are closed after each operation.
    """

    def __init__(self, repository_root: str):
        self._root = str(Path(repository_root).resolve())
        self._coordinator = FullRebuildCoordinator(self._root)

    # ── Context managers ───────────────────────────────────────────────

    def _open_db(self) -> SQLiteStore:
        """Open the active generation's SQLite database.

        Raises RepositoryNotIndexedError if no active generation exists.
        """
        try:
            generation = self._coordinator.active_generation()
        except FullRebuildError as exc:
            raise RepositoryNotIndexedError(
                f"Repository at {self._root} has an invalid or missing index."
            ) from exc
        if generation is None:
            raise RepositoryNotIndexedError(
                f"Repository at {self._root} has no active index."
            )
        db_path = str(
            self._coordinator.workspace / "generations" / generation / "index.db"
        )
        store = SQLiteStore(db_path)
        try:
            store.connect()
        except Exception as exc:
            raise RepositoryNotIndexedError(
                f"Cannot open index database for {self._root}."
            ) from exc
        return store

    def _open_chroma(self) -> ChromaStore:
        """Open the active generation's Chroma store."""
        try:
            gen = self._coordinator.active_generation()
        except FullRebuildError as exc:
            raise RepositoryNotIndexedError(
                f"Repository at {self._root} has an invalid or missing index."
            ) from exc
        if gen is None:
            raise RepositoryNotIndexedError(
                f"Repository at {self._root} has no active index."
            )
        chroma_path = str(
            self._coordinator.workspace / "generations" / gen / "chroma"
        )
        store = ChromaStore(chroma_path)
        try:
            store.open()
        except Exception as exc:
            raise RepositoryNotIndexedError(
                f"Cannot open Chroma store for {self._root}."
            ) from exc
        return store

    def _resolve_repo_id(self, store: SQLiteStore) -> str:
        repo_id = store.find_repository(self._root)
        if repo_id is None:
            raise RepositoryNotIndexedError(
                f"Repository {self._root} is not registered in the active index."
            )
        return repo_id

    # ── A. Repository summary ──────────────────────────────────────────

    def get_repository_summary(self) -> RepositorySummary:
        """Return a summary of the active index for this repository."""
        try:
            gen = self._coordinator.active_generation()
        except FullRebuildError as exc:
            raise RepositoryNotIndexedError(str(exc)) from exc
        if gen is None:
            raise RepositoryNotIndexedError("No active index.")

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            row = store.read_index_status(repo_id)
            if row is None or row.get("status") != "complete":
                raise RepositoryNotIndexedError("Active index is not complete.")

            count_fields = IndexCounts.__dataclass_fields__
            if any(
                f"count_{field}" not in row or row[f"count_{field}"] is None
                for field in count_fields
            ):
                raise RepositoryNotIndexedError(
                    "Active index status is incomplete."
                )

            counts = IndexCounts(
                **{field: row[f"count_{field}"] for field in count_fields}
            )

            indexed_at = row.get("completed_at")

            fts_enabled = False
            parsed_count = 0
            not_applicable_count = 0
            parse_error_count = 0
            import_count = 0
            route_count = 0
            test_count = 0

            parsed_count = self._count_by_parse_status(store, repo_id, "parsed")
            not_applicable_count = self._count_by_parse_status(
                store, repo_id, "not_applicable"
            )
            parse_error_count = self._count_by_parse_status(store, repo_id, "error")

            try:
                import_count = self._count_import_nodes(store, repo_id)
            except Exception:
                pass

            try:
                route_count = self._count_routes(store, repo_id)
            except Exception:
                pass

            try:
                test_count = self._count_test_nodes(store, repo_id)
            except Exception:
                pass

            return RepositorySummary(
                repository_root=self._root,
                active_generation_id=gen,
                index_status="complete",
                indexed_at=indexed_at,
                file_count=counts.scanned,
                parsed_count=parsed_count,
                not_applicable_count=not_applicable_count,
                error_count=parse_error_count,
                symbol_count=counts.symbols,
                import_count=import_count,
                route_count=route_count,
                test_count=test_count,
                chunk_count=counts.chunks,
                graph_node_count=counts.graph_nodes,
                graph_edge_count=counts.graph_edges,
                warning_count=counts.warnings,
                fatal_error_count=counts.errors,
            )
        finally:
            store.close()

    # ── B. Code search ─────────────────────────────────────────────────

    def search_code(
        self,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        mode: str = "hybrid",
    ) -> list[CodeSearchResult]:
        """Search code chunks by text, semantic, or hybrid mode."""
        self._validate_query(query)
        self._validate_limit(limit)
        mode = mode.lower()
        if mode not in ("text", "semantic", "hybrid"):
            raise QueryValidationError(
                f"Unsupported search mode '{mode}'. Use text, semantic, or hybrid."
            )

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            fts = FTSStore(store.conn)

            text_results: list[CodeSearchResult] = []
            semantic_results: list[CodeSearchResult] = []

            if mode in ("text", "hybrid"):
                text_results = self._text_search(fts, store.conn, query, repo_id, limit)

            if mode in ("semantic", "hybrid"):
                try:
                    semantic_results = self._semantic_search(query, repo_id, limit)
                except QueryValidationError:
                    if mode == "semantic":
                        raise
            if mode == "text":
                return text_results
            if mode == "semantic":
                return semantic_results

            return self._hybrid_merge(text_results, semantic_results, limit)
        finally:
            store.close()

    def _text_search(
        self,
        fts: FTSStore,
        conn: sqlite3.Connection,
        query: str,
        repo_id: str,
        limit: int,
    ) -> list[CodeSearchResult]:
        raw = fts.search_chunks(conn, query, repo_id, limit)
        results: list[CodeSearchResult] = []
        for row in raw:
            text_s = self._fts_score_to_similarity(row.get("rank"))
            results.append(
                CodeSearchResult(
                    chunk_id=row["id"],
                    source_path=self._normalize_path(row.get("file_path", "")),
                    start_line=row.get("start_line", 0) or 0,
                    end_line=row.get("end_line", 0) or 0,
                    chunk_kind=row.get("chunk_type", ""),
                    owner_semantic_key=row.get("symbol_name") or None,
                    display_text=(row.get("content") or "")[:500],
                    text_score=text_s,
                    semantic_score=None,
                    combined_score=text_s,
                    match_source="text",
                )
            )
        return results

    def _semantic_search(
        self,
        query: str,
        repo_id: str,
        limit: int,
    ) -> list[CodeSearchResult]:
        encoder = EmbeddingEncoder()
        try:
            encoder.ensure_available()
        except EmbeddingEncoderError as exc:
            raise QueryValidationError(
                "Semantic search is unavailable: the embedding model could not be loaded."
            ) from exc

        inp = EmbeddingInput(
            chunk_id="query",
            content=query,
            metadata=EmbeddingMetadata(
                chunk_id="query",
                file_path="query",
                symbol_name="",
                chunk_type=ChunkType.FILE_SUMMARY,
            ),
        )
        batch = encoder.encode([inp])
        if not batch.records:
            return []
        vector = batch.records[0].vector

        chroma = self._open_chroma()
        try:
            raw = chroma.collection.query(
                query_embeddings=[vector],
                n_results=SEMANTIC_SEARCH_LIMIT,
                where={"repo_id": repo_id},
                include=["metadatas", "distances"],
            )
        finally:
            chroma.close()

        results: list[CodeSearchResult] = []
        ids = raw.get("ids", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for cid, meta, dist in zip(ids, metadatas, distances):
            if meta is None:
                continue
            semantic_s = 1.0 - float(dist)
            semantic_s = max(0.0, min(1.0, semantic_s))
            fpath = str(meta.get("file_path", ""))
            results.append(
                CodeSearchResult(
                    chunk_id=str(cid),
                    source_path=self._normalize_path(fpath),
                    start_line=int(meta.get("start_line", 0) or 0),
                    end_line=int(meta.get("end_line", 0) or 0),
                    chunk_kind=str(meta.get("chunk_type", "")),
                    owner_semantic_key=meta.get("symbol_name") or None,
                    display_text="",
                    text_score=None,
                    semantic_score=semantic_s,
                    combined_score=semantic_s,
                    match_source="semantic",
                )
            )
        return results

    # ponytail: naive hybrid merge — deduplicate by chunk_id, max score, stable sort
    def _hybrid_merge(
        self,
        text_results: list[CodeSearchResult],
        semantic_results: list[CodeSearchResult],
        limit: int,
    ) -> list[CodeSearchResult]:
        seen: dict[str, CodeSearchResult] = {}

        for r in text_results:
            seen[r.chunk_id] = r

        for r in semantic_results:
            if r.chunk_id in seen:
                existing = seen[r.chunk_id]
                t_score = existing.text_score or 0.0
                s_score = r.semantic_score or 0.0
                combined = max(t_score, s_score)
                seen[r.chunk_id] = CodeSearchResult(
                    chunk_id=r.chunk_id,
                    source_path=r.source_path,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    chunk_kind=r.chunk_kind,
                    owner_semantic_key=r.owner_semantic_key or existing.owner_semantic_key,
                    display_text=existing.display_text or r.display_text,
                    text_score=existing.text_score,
                    semantic_score=r.semantic_score,
                    combined_score=combined,
                    match_source="both",
                )
            else:
                seen[r.chunk_id] = r

        sorted_results = sorted(
            seen.values(),
            key=lambda x: (-x.combined_score, x.chunk_id),
        )
        return sorted_results[:limit]

    # ── C. Symbol lookup ───────────────────────────────────────────────

    def find_symbols(
        self,
        query: str,
        limit: int = DEFAULT_SYMBOL_LIMIT,
        exact: bool = False,
    ) -> list[SymbolRecord]:
        self._validate_query(query)
        self._validate_limit(limit)

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            conn = store.conn

            if exact:
                rows = conn.execute(
                    """SELECT s.id, s.symbol_type, s.name, s.qualified_name,
                              s.start_line, s.end_line, s.parent_symbol_id,
                              f.path AS file_path
                       FROM symbols s
                       JOIN files f ON f.id = s.file_id
                       WHERE s.repo_id = ?
                         AND (s.qualified_name = ? OR s.name = ?)
                       ORDER BY s.start_line
                       LIMIT ?""",
                    (repo_id, query, query, limit),
                ).fetchall()
            else:
                pattern = f"%{query}%"
                rows = conn.execute(
                    """SELECT s.id, s.symbol_type, s.name, s.qualified_name,
                              s.start_line, s.end_line, s.parent_symbol_id,
                              f.path AS file_path
                       FROM symbols s
                       JOIN files f ON f.id = s.file_id
                       WHERE s.repo_id = ?
                         AND (s.name LIKE ? OR s.qualified_name LIKE ? OR f.path LIKE ?)
                       ORDER BY
                         CASE
                           WHEN s.qualified_name = ? THEN 0
                           WHEN s.name = ? THEN 1
                           ELSE 2
                         END,
                         s.start_line
                       LIMIT ?""",
                    (repo_id, pattern, pattern, pattern, query, query, limit),
                ).fetchall()

            return [
                SymbolRecord(
                    semantic_key=row["id"],
                    kind=row["symbol_type"],
                    qualified_name=row["qualified_name"] or row["name"],
                    source_path=self._normalize_path(row["file_path"]),
                    start_line=row["start_line"] or 0,
                    end_line=row["end_line"] or 0,
                    parent_semantic_key=self._row_get(row, "parent_symbol_id"),
                )
                for row in rows
            ]
        finally:
            store.close()

    # ── D. Route lookup ────────────────────────────────────────────────

    def find_routes(
        self,
        method: Optional[str] = None,
        path_query: Optional[str] = None,
        handler_query: Optional[str] = None,
        limit: int = DEFAULT_ROUTE_LIMIT,
    ) -> list[RouteRecord]:
        self._validate_limit(limit)

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            conn = store.conn

            where_clauses = ["s.repo_id = ?", "s.symbol_type = 'route'"]
            params: list[Any] = [repo_id]

            if method:
                method_upper = method.upper()
                where_clauses.append("s.name LIKE ?")
                params.append(f"{method_upper}%")

            if path_query:
                where_clauses.append("s.name LIKE ?")
                params.append(f"%{path_query}%")

            if handler_query:
                where_clauses.append("s.qualified_name LIKE ?")
                params.append(f"%{handler_query}%")

            sql = f"""SELECT s.id, s.name, s.qualified_name, s.start_line, s.end_line,
                             s.signature, s.metadata,
                             f.path AS file_path
                      FROM symbols s
                      JOIN files f ON f.id = s.file_id
                      WHERE {' AND '.join(where_clauses)}
                      ORDER BY s.start_line
                      LIMIT ?"""
            params.append(limit)
            rows = conn.execute(sql, tuple(params)).fetchall()

            results: list[RouteRecord] = []
            for row in rows:
                meta: Any = {}
                try:
                    meta_raw = self._row_get(row, "metadata")
                    if isinstance(meta_raw, str):
                        meta = json.loads(meta_raw)
                    elif isinstance(meta_raw, dict):
                        meta = meta_raw
                except (json.JSONDecodeError, TypeError):
                    pass
                if not isinstance(meta, dict):
                    meta = {}

                http_method = (meta.get("http_method") or
                               row["name"].split(" ")[0] if " " in (row["name"] or "") else "GET")
                route_path = (meta.get("route_path") or
                              " ".join(row["name"].split(" ")[1:]) if " " in (row["name"] or "") else "")
                handler_name = meta.get("handler_function") or row["qualified_name"] or ""

                results.append(
                    RouteRecord(
                        http_method=str(http_method).upper(),
                        route_path=str(route_path),
                        handler_semantic_key=str(handler_name),
                        handler_name=str(handler_name).split(".")[-1] if "." in str(handler_name) else str(handler_name),
                        source_path=self._normalize_path(row["file_path"]),
                        decorator_line=row["start_line"] or 0,
                        handler_start_line=row["start_line"] or 0,
                        handler_end_line=row["end_line"] or 0,
                    )
                )
            return results
        finally:
            store.close()

    # ── E. Related-code lookup ─────────────────────────────────────────

    def get_related(
        self,
        semantic_key: str,
        direction: str = "both",
        edge_types: Optional[list[str]] = None,
        depth: int = 1,
        limit: int = DEFAULT_RELATED_LIMIT,
    ) -> list[RelatedNode]:
        self._validate_query(semantic_key)
        self._validate_limit(limit)

        if depth < 1:
            raise QueryValidationError("depth must be at least 1")
        if depth > 1:
            raise QueryValidationError(
                "depth > 1 is not supported in the prototype. Use depth=1."
            )

        dirs = {"outgoing", "incoming", "both"}
        if direction.lower() not in dirs:
            raise QueryValidationError(
                f"direction must be one of: {', '.join(sorted(dirs))}"
            )

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            conn = store.conn

            node = conn.execute(
                "SELECT node_id, node_type, label FROM code_nodes WHERE repo_id = ? AND id = ?",
                (repo_id, semantic_key),
            ).fetchone()
            if node is None:
                node = conn.execute(
                    "SELECT node_id, node_type, label FROM code_nodes WHERE repo_id = ? AND node_id = ?",
                    (repo_id, semantic_key),
                ).fetchone()
            if node is None:
                return []

            node_id = node["node_id"]
            results: list[RelatedNode] = []

            if direction in ("outgoing", "both"):
                sql = """SELECT e.relation, e.confidence, e.metadata,
                                n.node_id, n.node_type, n.label, n.source_file
                         FROM code_edges e
                         JOIN code_nodes n ON n.repo_id = e.repo_id AND n.node_id = e.target_node_id
                         WHERE e.repo_id = ? AND e.source_node_id = ?
                           AND (e.relation IN (""" + self._edge_filter(edge_types) + """))
                         ORDER BY e.relation"""
                edge_rows = conn.execute(sql, (repo_id, node_id)).fetchall()
                for er in edge_rows:
                    results.append(self._row_to_related(er, "outgoing"))
                    if len(results) >= limit:
                        break

            if direction in ("incoming", "both") and len(results) < limit:
                sql = """SELECT e.relation, e.confidence, e.metadata,
                                n.node_id, n.node_type, n.label, n.source_file
                         FROM code_edges e
                         JOIN code_nodes n ON n.repo_id = e.repo_id AND n.node_id = e.source_node_id
                         WHERE e.repo_id = ? AND e.target_node_id = ?
                           AND (e.relation IN (""" + self._edge_filter(edge_types) + """))
                         ORDER BY e.relation"""
                edge_rows = conn.execute(sql, (repo_id, node_id)).fetchall()
                for er in edge_rows:
                    results.append(self._row_to_related(er, "incoming"))
                    if len(results) >= limit:
                        break

            return results[:limit]
        finally:
            store.close()

    # ── F. Impact analysis ─────────────────────────────────────────────

    def analyze_change_impact(
        self,
        semantic_key: str,
        limit: int = DEFAULT_IMPACT_LIMIT,
    ) -> ImpactAnalysis:
        self._validate_query(semantic_key)
        self._validate_limit(limit)

        store = self._open_db()
        try:
            repo_id = self._resolve_repo_id(store)
            conn = store.conn

            node = conn.execute(
                """SELECT n.id, n.node_id, n.node_type, n.label, n.source_file
                   FROM code_nodes n
                   WHERE n.repo_id = ? AND n.id = ?""",
                (repo_id, semantic_key),
            ).fetchone()
            if node is None:
                node = conn.execute(
                    """SELECT n.id, n.node_id, n.node_type, n.label, n.source_file
                       FROM code_nodes n
                       WHERE n.repo_id = ? AND n.node_id = ?""",
                    (repo_id, semantic_key),
                ).fetchone()

            if node is None:
                return ImpactAnalysis(
                    target_semantic_key=semantic_key,
                    target_kind="unknown",
                    target_qualified_name=semantic_key,
                    target_source_path="",
                    analysis_type="first_order",
                    warnings=["Symbol not found in the active index."],
                )

            nid = node["id"]
            node_id_val = node["node_id"]
            node_type = node["node_type"]
            label = node["label"] or ""
            source_file = node["source_file"] or ""

            # Direct callers (incoming 'calls' edges)
            callers_raw = conn.execute(
                """SELECT e.relation, sn.id, sn.node_type, sn.label, sn.source_file
                   FROM code_edges e
                   JOIN code_nodes sn ON sn.repo_id = e.repo_id AND sn.node_id = e.source_node_id
                   WHERE e.repo_id = ? AND e.target_node_id = ? AND e.relation = 'calls'
                   LIMIT ?""",
                (repo_id, node_id_val, limit),
            ).fetchall()

            callers = [
                SymbolRecord(
                    semantic_key=r["id"],
                    kind=r["node_type"],
                    qualified_name=r["label"] or "",
                    source_path=self._normalize_path(r["source_file"]),
                    start_line=0,
                    end_line=0,
                    parent_semantic_key=None,
                )
                for r in callers_raw
            ]

            # Direct callees (outgoing 'calls' edges)
            callees_raw = conn.execute(
                """SELECT e.relation, tn.id, tn.node_type, tn.label, tn.source_file
                   FROM code_edges e
                   JOIN code_nodes tn ON tn.repo_id = e.repo_id AND tn.node_id = e.target_node_id
                   WHERE e.repo_id = ? AND e.source_node_id = ? AND e.relation = 'calls'
                   LIMIT ?""",
                (repo_id, node_id_val, limit),
            ).fetchall()

            callees = [
                SymbolRecord(
                    semantic_key=r["id"],
                    kind=r["node_type"],
                    qualified_name=r["label"] or "",
                    source_path=self._normalize_path(r["source_file"]),
                    start_line=0,
                    end_line=0,
                    parent_semantic_key=None,
                )
                for r in callees_raw
            ]

            # Containing file (defines edge incoming)
            file_row = conn.execute(
                """SELECT sn.source_file
                   FROM code_edges e
                   JOIN code_nodes sn ON sn.repo_id = e.repo_id AND sn.node_id = e.source_node_id
                   WHERE e.repo_id = ? AND e.target_node_id = ?
                     AND e.relation = 'defines' AND sn.node_type = 'file'
                   LIMIT 1""",
                (repo_id, node_id_val),
            ).fetchone()
            containing_file = self._normalize_path(file_row["source_file"]) if file_row else self._normalize_path(source_file) if source_file else None

            # Containing class (defines edge from class to this)
            class_row = conn.execute(
                """SELECT sn.label
                   FROM code_edges e
                   JOIN code_nodes sn ON sn.repo_id = e.repo_id AND sn.node_id = e.source_node_id
                   WHERE e.repo_id = ? AND e.target_node_id = ?
                     AND e.relation = 'defines' AND sn.node_type = 'class'
                   LIMIT 1""",
                (repo_id, node_id_val),
            ).fetchone()
            containing_class = class_row["label"] if class_row else None

            # Import relationships
            import_rels = list(self._get_related_safe(
                store, repo_id, node_id_val, "imports", limit
            ))

            # Route relationships
            route_rels = list(self._get_related_safe(
                store, repo_id, node_id_val, "handles_route", limit
            ))

            # Related tests (only if node is a function/class/method)
            related_tests: list[SymbolRecord] = []
            if node_type in ("function", "class", "method"):
                test_rows = conn.execute(
                    """SELECT tn.id, tn.node_type, tn.label, tn.source_file
                       FROM code_edges e
                       JOIN code_nodes tn ON tn.repo_id = e.repo_id AND tn.node_id = e.target_node_id
                       WHERE e.repo_id = ? AND e.source_node_id = ?
                         AND e.relation = 'tests'
                       LIMIT ?""",
                    (repo_id, node_id_val, limit),
                ).fetchall()
                related_tests = [
                    SymbolRecord(
                        semantic_key=r["id"],
                        kind=r["node_type"],
                        qualified_name=r["label"] or "",
                        source_path=self._normalize_path(r["source_file"]),
                        start_line=0,
                        end_line=0,
                        parent_semantic_key=None,
                    )
                    for r in test_rows
                ]

            warnings: list[str] = []
            if containing_file is None:
                warnings.append("No containing file relationship found.")
            if not import_rels:
                warnings.append(
                    "No import relationships found (imports may not be stored as graph edges for this node type)."
                )
            if not route_rels:
                warnings.append(
                    "No route relationships found (node is not a route handler or no routes reference it)."
                )
            if not related_tests:
                warnings.append(
                    "No directly related tests found (test relationships are inferred by naming convention only)."
                )

            return ImpactAnalysis(
                target_semantic_key=nid,
                target_kind=node_type,
                target_qualified_name=label,
                target_source_path=self._normalize_path(source_file),
                analysis_type="first_order",
                direct_callers=callers,
                direct_callees=callees,
                containing_file=containing_file,
                containing_class=containing_class,
                import_relationships=list(import_rels),
                route_relationships=list(route_rels),
                related_tests=related_tests,
                warnings=warnings,
            )
        finally:
            store.close()

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
        try:
            return row[key]
        except (KeyError, IndexError):
            return default

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return ""
        return path.replace("\\", "/")

    @staticmethod
    def _validate_query(query: str) -> None:
        if not query or not query.strip():
            raise QueryValidationError("Query must not be blank.")

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not isinstance(limit, int) or limit < 1:
            raise QueryValidationError("Limit must be a positive integer.")
        if limit > MAX_LIMIT:
            raise QueryValidationError(f"Limit must not exceed {MAX_LIMIT}.")

    @staticmethod
    def _fts_score_to_similarity(rank: Any) -> float:
        try:
            fts_rank = float(rank)
            score = 1.0 / (1.0 + abs(fts_rank))
            return max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _edge_filter(edge_types: Optional[list[str]]) -> str:
        valid = list(GraphRelation.__members__.values())
        if edge_types:
            filtered = [et for et in edge_types if et in valid]
            if not filtered:
                filtered = valid
        else:
            filtered = valid
        placeholders = ", ".join(f"'{v}'" for v in (e.value if hasattr(e, 'value') else e for e in filtered))
        return placeholders

    @staticmethod
    def _row_to_related(row: sqlite3.Row, direction: str) -> RelatedNode:
        meta_raw = None
        try:
            meta_raw = row["metadata"]
        except (KeyError, IndexError):
            pass
        qualifier: Optional[str] = None
        if meta_raw:
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                if isinstance(meta, dict):
                    qualifier = meta.get("qualifier")
            except (json.JSONDecodeError, TypeError):
                pass
        relation = row["relation"]
        confidence = None
        try:
            confidence = row["confidence"]
        except (KeyError, IndexError):
            pass
        if qualifier is None and confidence:
            qualifier = confidence
        source_path = ""
        try:
            source_path = row["source_file"] or ""
        except (KeyError, IndexError):
            pass
        return RelatedNode(
            center_identity="",
            related_node_identity=row["node_id"],
            node_kind=row["node_type"],
            qualified_name=row["label"] or "",
            source_path=source_path,
            relationship_type=relation,
            direction=direction,
            qualifier=qualifier,
        )

    def _get_related_safe(
        self,
        store: SQLiteStore,
        repo_id: str,
        node_id: str,
        relation: str,
        limit: int,
    ) -> list[RelatedNode]:
        rows = store.conn.execute(
            """SELECT e.relation, e.confidence, e.metadata,
                      n.node_id, n.node_type, n.label, n.source_file
               FROM code_edges e
               JOIN code_nodes n ON n.repo_id = e.repo_id AND n.node_id = e.target_node_id
               WHERE e.repo_id = ? AND e.source_node_id = ? AND e.relation = ?
               LIMIT ?""",
            (repo_id, node_id, relation, limit),
        ).fetchall()
        return [self._row_to_related(r, "outgoing") for r in rows]

    def _count_import_nodes(self, store: SQLiteStore, repo_id: str) -> int:
        row = store.conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_nodes WHERE repo_id = ? AND node_type = 'import'",
            (repo_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _count_routes(self, store: SQLiteStore, repo_id: str) -> int:
        row = store.conn.execute(
            "SELECT COUNT(*) AS cnt FROM symbols WHERE repo_id = ? AND symbol_type = 'route'",
            (repo_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _count_test_nodes(self, store: SQLiteStore, repo_id: str) -> int:
        row = store.conn.execute(
            "SELECT COUNT(*) AS cnt FROM code_nodes WHERE repo_id = ? AND node_type = 'test'",
            (repo_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _count_by_parse_status(self, store: SQLiteStore, repo_id: str, status: str) -> int:
        row = store.conn.execute(
            "SELECT COUNT(*) AS cnt FROM files WHERE repo_id = ? AND parse_status = ?",
            (repo_id, status),
        ).fetchone()
        return row["cnt"] if row else 0
