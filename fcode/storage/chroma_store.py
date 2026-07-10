"""Chroma vector storage — local persistent client with repository isolation."""

import os
from typing import Any, Optional

from fcode.contracts.interfaces import ChromaStoreProtocol
from fcode.contracts.models import EmbeddingRecord

COLLECTION_NAME = "code_chunks"
EXPECTED_DIMENSION = 384


class ChromaStore:
    """Chroma vector store for chunk embeddings.

    Uses local PersistentClient. Collection is named 'code_chunks'.
    All vectors include repo_id metadata for repository isolation.
    """

    def __init__(self, chroma_path: str):
        self._chroma_path = chroma_path
        self._client: Any = None
        self._collection: Any = None

    def open(self) -> None:
        import chromadb
        os.makedirs(self._chroma_path, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def close(self) -> None:
        self._collection = None
        self._client = None

    @property
    def collection(self) -> Any:
        if self._collection is None:
            raise RuntimeError("ChromaStore not open. Call open() first.")
        return self._collection

    # ── Repository isolation ────────────────────────────────────────────────

    def delete_repository_vectors(self, repo_id: str) -> None:
        self.collection.delete(where={"repo_id": repo_id})

    # ── Upsert ──────────────────────────────────────────────────────────────

    def upsert_embeddings(self, repo_id: str, records: list[EmbeddingRecord]) -> None:
        if not records:
            return
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        documents: list[str] = []

        for rec in records:
            if len(rec.vector) != EXPECTED_DIMENSION:
                raise ValueError(
                    f"Expected {EXPECTED_DIMENSION}-dimensional vector, "
                    f"got {len(rec.vector)}"
                )
            meta = {
                "chunk_id": rec.metadata.chunk_id,
                "repo_id": repo_id,
                "file_path": rec.metadata.source_file or "",
                "symbol_name": rec.metadata.symbol_name if hasattr(rec.metadata, "symbol_name") else "",
                "chunk_type": rec.metadata.chunk_type.value if hasattr(rec.metadata.chunk_type, "value") else str(rec.metadata.chunk_type),
                "language": rec.metadata.language if hasattr(rec.metadata, "language") else "",
                "start_line": rec.metadata.start_line,
                "end_line": rec.metadata.end_line,
            }
            ids.append(rec.metadata.chunk_id)
            embeddings.append(rec.vector)
            metadatas.append(meta)
            documents.append(
                rec.metadata.source_file if hasattr(rec.metadata, "source_file") else ""
            )

        if ids:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents,
            )

    # ── Count ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self.collection.count()

    def count_vectors(self, repo_id: str) -> int:
        results = self.collection.get(where={"repo_id": repo_id})
        return len(results["ids"]) if results and results["ids"] else 0

    # ── ChromaStoreProtocol conformance ─────────────────────────────────────

    def store_embeddings(self, records: list[EmbeddingRecord]) -> None:
        if not records:
            return
        repo_id = records[0].metadata.source_file if hasattr(records[0].metadata, "source_file") else ""
        self.upsert_embeddings(repo_id, records)

    def reset(self) -> None:
        try:
            self.collection.delete(where={})
        except Exception:
            pass
