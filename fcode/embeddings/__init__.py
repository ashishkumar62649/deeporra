"""F Code local embeddings — Sentence Transformers encoding (CPU, offline)."""

from fcode.embeddings.encoder import (
    EmbeddingEncoder,
    EmbeddingEncoderError,
    build_embedding_inputs,
)

__all__ = [
    "EmbeddingEncoder",
    "EmbeddingEncoderError",
    "build_embedding_inputs",
]
