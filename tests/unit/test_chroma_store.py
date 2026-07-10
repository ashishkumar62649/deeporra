"""Unit tests for ChromaStore."""

import os
import tempfile

import pytest

from fcode.contracts.models import EmbeddingRecord, EmbeddingMetadata
from fcode.contracts.enums import ChunkType


def _can_import_chroma():
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture
def chroma_path():
    tmp = tempfile.mkdtemp()
    return os.path.join(tmp, "chroma")


@pytest.fixture
def store(chroma_path):
    if not _can_import_chroma():
        pytest.skip("chromadb not installed")
    from fcode.storage.chroma_store import ChromaStore
    s = ChromaStore(chroma_path)
    s.open()
    yield s
    try:
        s.close()
    except Exception:
        pass


class TestChromaBasic:
    def test_local_collection_opens(self, store):
        assert store.collection.name == "code_chunks"

    def test_upsert_stores_records(self, store):
        rec = EmbeddingRecord(
            chunk_id="test-1",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="test.py",
                chunk_id="test-1",
                chunk_type=ChunkType.FILE_SUMMARY,
                start_line=1,
                end_line=10,
            ),
        )
        store.upsert_embeddings("repo-1", [rec])
        assert store.count_vectors("repo-1") == 1

    def test_repeated_upsert_replaces(self, store):
        rec1 = EmbeddingRecord(
            chunk_id="dup-1",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="a.py", chunk_id="dup-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        rec2 = EmbeddingRecord(
            chunk_id="dup-1",
            vector=[0.2] * 384,
            metadata=EmbeddingMetadata(
                source_file="b.py", chunk_id="dup-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-1", [rec1])
        store.upsert_embeddings("repo-1", [rec2])
        assert store.count_vectors("repo-1") == 1


class TestRepositoryIsolation:
    def test_repo_specific_count(self, store):
        rec1 = EmbeddingRecord(
            chunk_id="r1-1",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="a.py", chunk_id="r1-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        rec2 = EmbeddingRecord(
            chunk_id="r2-1",
            vector=[0.2] * 384,
            metadata=EmbeddingMetadata(
                source_file="b.py", chunk_id="r2-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-a", [rec1])
        store.upsert_embeddings("repo-b", [rec2])
        assert store.count_vectors("repo-a") == 1
        assert store.count_vectors("repo-b") == 1

    def test_delete_does_not_affect_other_repo(self, store):
        rec1 = EmbeddingRecord(
            chunk_id="del-1",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="a.py", chunk_id="del-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        rec2 = EmbeddingRecord(
            chunk_id="del-2",
            vector=[0.2] * 384,
            metadata=EmbeddingMetadata(
                source_file="b.py", chunk_id="del-2",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-x", [rec1])
        store.upsert_embeddings("repo-y", [rec2])
        store.delete_repository_vectors("repo-x")
        assert store.count_vectors("repo-x") == 0
        assert store.count_vectors("repo-y") == 1


class TestVectorValidation:
    def test_384_dimension_accepted(self, store):
        rec = EmbeddingRecord(
            chunk_id="dim-ok",
            vector=[0.5] * 384,
            metadata=EmbeddingMetadata(
                source_file="d.py", chunk_id="dim-ok",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-d", [rec])
        assert store.count_vectors("repo-d") == 1

    def test_wrong_dimension_rejected(self, store):
        rec = EmbeddingRecord(
            chunk_id="dim-bad",
            vector=[0.5] * 100,
            metadata=EmbeddingMetadata(
                source_file="d.py", chunk_id="dim-bad",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        with pytest.raises(ValueError, match="384"):
            store.upsert_embeddings("repo-d", [rec])


class TestMetadata:
    def test_absent_symbol_name_empty_string(self, store):
        rec = EmbeddingRecord(
            chunk_id="no-sym",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="n.py", chunk_id="no-sym",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-n", [rec])
        results = store.collection.get(where={"repo_id": "repo-n"})
        assert results["metadatas"][0]["symbol_name"] == ""

    def test_absent_language_empty_string(self, store):
        rec = EmbeddingRecord(
            chunk_id="no-lang",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="l.py", chunk_id="no-lang",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-l", [rec])
        results = store.collection.get(where={"repo_id": "repo-l"})
        assert results["metadatas"][0]["language"] == ""

    def test_no_null_metadata_values(self, store):
        rec = EmbeddingRecord(
            chunk_id="no-null",
            vector=[0.1] * 384,
            metadata=EmbeddingMetadata(
                source_file="nn.py", chunk_id="no-null",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        store.upsert_embeddings("repo-nn", [rec])
        results = store.collection.get(where={"repo_id": "repo-nn"})
        meta = results["metadatas"][0]
        for v in meta.values():
            assert v is not None, f"Metadata value is None: {meta}"


class TestPersistence:
    def test_persistence_survives_reopen(self, chroma_path):
        if not _can_import_chroma():
            pytest.skip("chromadb not installed")
        from fcode.storage.chroma_store import ChromaStore
        s1 = ChromaStore(chroma_path)
        s1.open()
        rec = EmbeddingRecord(
            chunk_id="persist-1",
            vector=[0.3] * 384,
            metadata=EmbeddingMetadata(
                source_file="p.py", chunk_id="persist-1",
                chunk_type=ChunkType.FILE_SUMMARY, start_line=1, end_line=5,
            ),
        )
        s1.upsert_embeddings("repo-p", [rec])
        s1.close()
        s2 = ChromaStore(chroma_path)
        s2.open()
        assert s2.count_vectors("repo-p") == 1
        s2.close()
