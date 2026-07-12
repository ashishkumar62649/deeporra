"""Local staged full-index rebuild and atomic active-generation promotion."""

from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from fcode.contracts import (
    CodeChunk,
    EmbeddingBatchResult,
    GraphBuildResult,
    IndexCounts,
    ParsedFile,
    ScanResult,
)
from fcode.indexing.sqlite_fts_persistence import run_step4_persistence
from fcode.storage.chroma_store import ChromaStore, EXPECTED_DIMENSION
from fcode.storage.fts_store import FTSStore
from fcode.storage.graph_store import GraphStore
from fcode.storage.sqlite_store import SQLiteStore


class FullRebuildError(RuntimeError):
    """Raised for a controlled staging, verification, or promotion failure."""


@dataclass(frozen=True)
class FullRebuildOutcome:
    cleanup_warning: bool = False


@dataclass(frozen=True)
class _GenerationPaths:
    root: Path
    database: Path
    chroma: Path


class FullRebuildCoordinator:
    """Build a complete generation without changing the active one in place."""

    def __init__(self, repo_path: str) -> None:
        self._workspace = Path(repo_path).resolve() / ".fcode"
        self._generations = self._workspace / "generations"
        self._staging = self._workspace / "staging"
        self._pointer = self._workspace / "active.json"
        self._guard = self._workspace / "rebuild.lock"

    @property
    def workspace(self) -> Path:
        return self._workspace

    def active_generation(self) -> str | None:
        if not self._pointer.exists():
            return None
        try:
            generation = json.loads(self._pointer.read_text(encoding="utf-8")).get(
                "generation"
            )
        except (OSError, ValueError, AttributeError) as exc:
            raise FullRebuildError("active generation metadata is invalid") from exc
        if not isinstance(generation, str) or not self._is_generation_name(generation):
            raise FullRebuildError("active generation metadata is invalid")
        if not (self._generations / generation).is_dir():
            raise FullRebuildError("active generation is unavailable")
        return generation

    def active_paths(self) -> _GenerationPaths:
        generation = self.active_generation()
        if generation is None:
            raise FullRebuildError("no active generation")
        return self._paths(self._generations / generation)

    def build(
        self,
        *,
        scan_result: ScanResult,
        parsed_files: list[ParsedFile],
        chunks: list[CodeChunk],
        embedding_result: EmbeddingBatchResult,
        graph_result: GraphBuildResult,
        counts: IndexCounts,
    ) -> FullRebuildOutcome:
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._acquire_guard()
        generation_path: Path | None = None
        marker: Path | None = None
        try:
            previous = self.active_generation()
            self._cleanup_stale_staging()
            self._staging.mkdir(exist_ok=True)
            self._generations.mkdir(exist_ok=True)
            generation = f"generation-{secrets.token_hex(12)}"
            generation_path = self._generations / generation
            marker = self._staging / f"{generation}.json"
            marker.write_text(json.dumps({"generation": generation}), encoding="utf-8")
            generation_path.mkdir()
            self._write_and_verify_stage(
                self._paths(generation_path),
                scan_result,
                parsed_files,
                chunks,
                embedding_result,
                graph_result,
                counts,
            )
            self._write_active(generation)
            try:
                self._verify_generation(
                    self._paths(generation_path), chunks, embedding_result, graph_result,
                    counts, require_complete=True,
                )
            except BaseException:
                self._restore_active(previous)
                raise

            cleanup_warning = False
            try:
                marker.unlink()
                if self._staging.exists() and not any(self._staging.iterdir()):
                    self._staging.rmdir()
            except OSError:
                cleanup_warning = True
            if previous is not None:
                try:
                    shutil.rmtree(self._generations / previous)
                except OSError:
                    cleanup_warning = True
            return FullRebuildOutcome(cleanup_warning=cleanup_warning)
        except BaseException:
            if marker is not None and marker.exists():
                marker.unlink(missing_ok=True)
            if generation_path is not None and generation_path.exists():
                active = self.active_generation() if self._pointer.exists() else None
                if active != generation_path.name:
                    shutil.rmtree(generation_path, ignore_errors=True)
            raise
        finally:
            self._release_guard()

    def _write_and_verify_stage(
        self,
        paths: _GenerationPaths,
        scan_result: ScanResult,
        parsed_files: list[ParsedFile],
        chunks: list[CodeChunk],
        embedding_result: EmbeddingBatchResult,
        graph_result: GraphBuildResult,
        counts: IndexCounts,
    ) -> None:
        sqlite_store = SQLiteStore(str(paths.database))
        chroma_store = ChromaStore(str(paths.chroma))
        try:
            sqlite_store.connect()
            fts_store = FTSStore(sqlite_store.conn)
            persisted = run_step4_persistence(
                scan_result,
                parsed_files,
                chunks,
                sqlite_store,
                fts_store,
                str(self._workspace.parent),
                warning_count=counts.warnings,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
            chroma_store.open()
            chroma_store.upsert_embeddings(persisted["repo_id"], embedding_result.records)
            graph_store = GraphStore(sqlite_store.conn)
            graph_store.store_graph(
                self._node_rows(persisted["repo_id"], graph_result),
                self._edge_rows(persisted["repo_id"], graph_result),
            )
            sqlite_store.commit_transaction()
        finally:
            chroma_store.close()
            sqlite_store.close()

        self._verify_generation(
            paths, chunks, embedding_result, graph_result, counts, require_complete=False
        )
        sqlite_store = SQLiteStore(str(paths.database))
        try:
            sqlite_store.connect()
            repo_id = sqlite_store.find_repository(str(self._workspace.parent))
            if repo_id is None:
                raise FullRebuildError("staged generation verification failed")
            sqlite_store.update_index_status(
                repo_id,
                status="complete",
                total_files=counts.scanned,
                indexed_files=counts.scanned,
                total_symbols=counts.symbols,
                total_chunks=counts.chunks,
                total_graph_nodes=counts.graph_nodes,
                total_edges=counts.graph_edges,
                total_vectors=embedding_result.success_count,
                warning_count=counts.warnings,
                error_count=0,
                **{f"count_{field}": getattr(counts, field) for field in counts.__dataclass_fields__},
            )
            sqlite_store.commit_transaction()
        finally:
            sqlite_store.close()
        self._verify_generation(
            paths, chunks, embedding_result, graph_result, counts, require_complete=True
        )

    def _verify_generation(
        self,
        paths: _GenerationPaths,
        chunks: list[CodeChunk],
        embedding_result: EmbeddingBatchResult,
        graph_result: GraphBuildResult,
        counts: IndexCounts,
        *,
        require_complete: bool,
    ) -> None:
        sqlite_store = SQLiteStore(str(paths.database))
        chroma_store = ChromaStore(str(paths.chroma))
        try:
            sqlite_store.connect()
            repo_id = sqlite_store.find_repository(str(self._workspace.parent))
            if repo_id is None or sqlite_store.foreign_key_violations():
                raise FullRebuildError("staged generation verification failed")
            expected_chunks = {chunk.chunk_id for chunk in chunks}
            if set(sqlite_store.get_chunk_ids(repo_id)) != expected_chunks:
                raise FullRebuildError("staged generation verification failed")
            status = sqlite_store.read_index_status(repo_id)
            if status is None or (require_complete and (
                status["status"] != "complete"
                or status["total_files"] != counts.scanned
                or status["total_chunks"] != counts.chunks
                or status["total_graph_nodes"] != counts.graph_nodes
                or status["total_edges"] != counts.graph_edges
                or status["total_vectors"] != embedding_result.success_count
                or any(status.get(f"count_{field}") != getattr(counts, field) for field in counts.__dataclass_fields__)
            )):
                raise FullRebuildError("staged generation verification failed")
            fts_store = FTSStore(sqlite_store.conn)
            fts_ids = set(fts_store.get_chunk_ids(sqlite_store.conn, repo_id))
            if not fts_ids.issubset(expected_chunks):
                raise FullRebuildError("staged generation verification failed")

            chroma_store.open()
            vectors = chroma_store.get_embeddings(repo_id)
            vector_id_list = list(vectors.get("ids") or [])
            vector_ids = set(vector_id_list)
            expected_vectors = {record.chunk_id for record in embedding_result.records}
            if (
                vector_ids != expected_vectors
                or len(vector_id_list) != len(vector_ids)
                or len(vector_ids) != embedding_result.success_count
            ):
                raise FullRebuildError("staged generation verification failed")
            metadatas = vectors.get("metadatas")
            embeddings = vectors.get("embeddings")
            metadatas = [] if metadatas is None else metadatas
            embeddings = [] if embeddings is None else embeddings
            for vector_id, metadata, vector in zip(vector_id_list, metadatas, embeddings):
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("chunk_id") != vector_id
                    or str(metadata.get("file_path", "")).startswith(("/", "\\"))
                    or len(vector) != EXPECTED_DIMENSION
                ):
                    raise FullRebuildError("staged generation verification failed")

            graph_store = GraphStore(sqlite_store.conn)
            nodes = graph_store.get_nodes(sqlite_store.conn, repo_id)
            edges = graph_store.get_edges(sqlite_store.conn, repo_id)
            if len(nodes) != graph_result.node_count or len(edges) != graph_result.edge_count:
                raise FullRebuildError("staged generation verification failed")
            if {node["id"] for node in nodes} != {node.record_id for node in graph_result.nodes}:
                raise FullRebuildError("staged generation verification failed")
            if {edge["id"] for edge in edges} != {edge.record_id for edge in graph_result.edges}:
                raise FullRebuildError("staged generation verification failed")
            node_ids = {node["node_id"] for node in nodes}
            if any(edge["source_node_id"] not in node_ids or edge["target_node_id"] not in node_ids for edge in edges):
                raise FullRebuildError("staged generation verification failed")
        finally:
            chroma_store.close()
            sqlite_store.close()

    @staticmethod
    def _node_rows(repo_id: str, graph_result: GraphBuildResult) -> list[dict]:
        return [
            {
                "id": node.record_id,
                "repo_id": repo_id,
                "node_id": node.node_id,
                "label": node.label,
                "node_type": node.node_type.value,
                "source_file": node.source_file,
                "source_location": node.source_location,
                "confidence": node.confidence.value,
                "metadata": node.metadata or node.properties,
            }
            for node in graph_result.nodes
        ]

    @staticmethod
    def _edge_rows(repo_id: str, graph_result: GraphBuildResult) -> list[dict]:
        return [
            {
                "id": edge.record_id,
                "repo_id": repo_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "relation": edge.relation.value,
                "confidence": edge.confidence.value,
                "source_file": edge.source_file,
                "metadata": edge.metadata or edge.properties,
            }
            for edge in graph_result.edges
        ]

    def _paths(self, root: Path) -> _GenerationPaths:
        return _GenerationPaths(root, root / "index.db", root / "chroma")

    def _cleanup_stale_staging(self) -> None:
        if not self._staging.exists():
            return
        active = self.active_generation()
        for child in self._staging.glob("generation-*.json"):
            try:
                generation = json.loads(child.read_text(encoding="utf-8")).get("generation")
            except (OSError, ValueError, AttributeError):
                continue
            if not isinstance(generation, str) or not self._is_generation_name(generation):
                continue
            if generation != active:
                shutil.rmtree(self._generations / generation, ignore_errors=True)
            child.unlink(missing_ok=True)

    def _acquire_guard(self) -> None:
        try:
            descriptor = os.open(self._guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise FullRebuildError("another rebuild is active") from exc
        os.close(descriptor)

    def _release_guard(self) -> None:
        try:
            self._guard.unlink()
        except FileNotFoundError:
            pass

    def _write_active(self, generation: str) -> None:
        temporary = self._pointer.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps({"generation": generation}), encoding="utf-8")
            temporary.replace(self._pointer)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _restore_active(self, generation: str | None) -> None:
        if generation is None:
            try:
                self._pointer.unlink()
            except FileNotFoundError:
                pass
        else:
            self._write_active(generation)

    @staticmethod
    def _is_generation_name(value: str) -> bool:
        return value.startswith("generation-") and value.replace("-", "").isalnum()
