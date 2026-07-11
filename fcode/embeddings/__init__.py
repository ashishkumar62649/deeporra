"""F Code local embeddings — Sentence Transformers encoding (CPU, offline)."""

from fcode.embeddings.encoder import (
    EmbeddingEncoder,
    EmbeddingEncoderError,
    EXPECTED_DIMENSION,
    build_embedding_inputs,
)

__all__ = [
    "EmbeddingEncoder",
    "EmbeddingEncoderError",
    "EXPECTED_DIMENSION",
    "build_embedding_inputs",
]
