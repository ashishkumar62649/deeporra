"""Local offline embedding encoder — Sentence Transformers on CPU.

Only operates on EmbeddingInput values. Never reads files, never makes
network calls. Model loads lazily at first encode or ensure_available call.
"""

import os
from typing import Any, Optional, Sequence

from fcode.contracts.enums import ChunkType, ParseStatus
from fcode.contracts.errors import ErrorCode
from fcode.contracts.models import (
    CodeChunk,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingMetadata,
    EmbeddingRecord,
)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EXPECTED_DIMENSION = 384
BATCH_SIZE = 100
MAX_EMBEDDING_BYTES = 100 * 1024
MAX_OVERSIZE_LINES = 100


class EmbeddingEncoderError(RuntimeError):
    """Raised when embedding fails irrecoverably."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        result: Optional[EmbeddingBatchResult] = None,
    ):
        self.code = code
        self.result = result
        super().__init__(message)

    def __str__(self) -> str:
        return self.args[0]


def build_embedding_inputs(
    chunks: Sequence[CodeChunk],
) -> list[EmbeddingInput]:
    """Convert CodeChunk values to EmbeddingInput values.

    Validates input fields and raises sanitized ValueError on invalid data.
    Preserves chunk ordering.
    Does not filter or modify original chunks.
    """
    results: list[EmbeddingInput] = []
    seen_chunk_ids: set[str] = set()

    for chunk in chunks:
        if not chunk.chunk_id:
            raise ValueError("chunk has empty chunk_id")
        if chunk.chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id")
        seen_chunk_ids.add(chunk.chunk_id)

        if chunk.start_line < 1 or chunk.end_line < chunk.start_line:
            raise ValueError(f"invalid line range in chunk {chunk.chunk_id}")
        fpath = chunk.file_path
        if not fpath:
            raise ValueError(f"empty file_path in chunk {chunk.chunk_id}")
        if fpath.startswith("/"):
            raise ValueError(f"absolute file_path in chunk {chunk.chunk_id}")
        if ".." in fpath.split("/"):
            raise ValueError(f"traversal file_path in chunk {chunk.chunk_id}")

        meta = chunk.metadata or {}
        if "has_secrets" not in meta:
            raise ValueError(f"missing has_secrets in chunk {chunk.chunk_id}")
        if not isinstance(meta["has_secrets"], bool):
            raise ValueError(f"non-boolean has_secrets in chunk {chunk.chunk_id}")

        raw_status = meta.get("parse_status", ParseStatus.NOT_APPLICABLE)
        if isinstance(raw_status, ParseStatus):
            parse_status = raw_status
        elif isinstance(raw_status, str):
            try:
                parse_status = ParseStatus(raw_status)
            except ValueError:
                raise ValueError(f"invalid parse_status in chunk {chunk.chunk_id}")
        else:
            raise ValueError(f"invalid parse_status type in chunk {chunk.chunk_id}")

        metadata = EmbeddingMetadata(
            chunk_id=chunk.chunk_id,
            file_path=fpath,
            symbol_name=chunk.symbol_name or "",
            chunk_type=chunk.chunk_type,
            language=chunk.language,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        )

        results.append(EmbeddingInput(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            metadata=metadata,
            has_secrets=meta["has_secrets"],
            parse_status=parse_status,
        ))

    return results


class EmbeddingEncoder:
    """Local Sentence Transformers encoder.

    Model loads lazily on first encode call or ensure_available call.
    CPU only, local-files-only, no download, no network.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._loaded_model_name: Optional[str] = None
        self._loaded_dimension: Optional[int] = None

    def ensure_available(self) -> None:
        """Load the model (once per instance) and validate dimension.

        Raises EmbeddingEncoderError if model is unavailable or
        reported dimension is not 384.
        """
        self._load_model()

    def encode(self, inputs: Sequence[EmbeddingInput]) -> EmbeddingBatchResult:
        """Encode eligible EmbeddingInput values into vectors.

        Returns EmbeddingBatchResult with records, warnings, counts.
        Raises EmbeddingEncoderError if all eligible chunks fail.
        """
        result = EmbeddingBatchResult()
        eligible: list[EmbeddingInput] = []
        skipped: list[EmbeddingInput] = []
        seen_ids: set[str] = set()

        self._validate_inputs(inputs, seen_ids)

        for inp in inputs:
            if not self._is_eligible(inp):
                result.skipped_count += 1
                skipped.append(inp)
            else:
                eligible.append(inp)

        result.eligible_count = len(eligible)

        if not eligible:
            return result

        self._load_model()

        for batch_start in range(0, len(eligible), BATCH_SIZE):
            batch = eligible[batch_start:batch_start + BATCH_SIZE]
            prepared = [self._prepare_content(inp) for inp in batch]

            try:
                vectors = self._model.encode(
                    prepared,
                    batch_size=BATCH_SIZE,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
            except Exception as exc:
                for inp in batch:
                    result.fail_count += 1
                    result.warnings.append({
                        "code": "embedding_chunk_warning",
                        "chunk_id": inp.chunk_id,
                        "message": "encoding failed",
                    })
                continue

            if len(vectors) != len(batch):
                raise EmbeddingEncoderError(
                    ErrorCode.EMBEDDING_FAILED,
                    "output count mismatch",
                )

            for inp, vec in zip(batch, vectors):
                validated = self._validate_vector(vec)
                result.records.append(EmbeddingRecord(
                    chunk_id=inp.chunk_id,
                    vector=validated,
                    metadata=inp.metadata,
                ))
                result.success_count += 1

        result.success_count = len(result.records)
        if result.eligible_count > 0 and result.success_count == 0:
            raise EmbeddingEncoderError(
                ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED,
                "all eligible chunks failed",
                result=result,
            )

        return result

    def _load_model(self) -> None:
        if self._model is not None:
            return
        old_hub = os.environ.get("HF_HUB_OFFLINE")
        old_tf = os.environ.get("TRANSFORMERS_OFFLINE")
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            from sentence_transformers import SentenceTransformer  # lazy
            self._model = SentenceTransformer(
                MODEL_NAME,
                device="cpu",
                local_files_only=True,
            )
        except Exception as exc:
            raise EmbeddingEncoderError(
                ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
                "model unavailable locally",
            )
        finally:
            if old_hub is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = old_hub
            if old_tf is None:
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
            else:
                os.environ["TRANSFORMERS_OFFLINE"] = old_tf

        dim = self._model.get_sentence_embedding_dimension()
        if dim != EXPECTED_DIMENSION:
            raise EmbeddingEncoderError(
                ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                f"model dimension {dim} != {EXPECTED_DIMENSION}",
            )
        self._loaded_dimension = dim

    @staticmethod
    def _validate_inputs(
        inputs: Sequence[EmbeddingInput],
        seen_ids: set[str],
    ) -> None:
        for inp in inputs:
            if not inp.chunk_id:
                raise ValueError("empty chunk_id")
            if inp.chunk_id in seen_ids:
                raise ValueError("duplicate chunk_id")
            seen_ids.add(inp.chunk_id)

            if inp.chunk_id != inp.metadata.chunk_id:
                raise ValueError("chunk_id mismatch in metadata")

            md = inp.metadata
            if md.start_line < 0 or md.end_line < md.start_line:
                raise ValueError("invalid metadata line range")

            fpath = md.file_path
            if not fpath:
                raise ValueError("empty metadata file_path")
            if fpath.startswith("/"):
                raise ValueError("absolute metadata file_path")
            if ".." in fpath.split("/"):
                raise ValueError("traversal metadata file_path")

            if not isinstance(md.chunk_type, ChunkType):
                raise ValueError("unsupported metadata chunk_type")

            if not isinstance(inp.content, str):
                raise ValueError("malformed input content type")

    @staticmethod
    def _is_eligible(inp: EmbeddingInput) -> bool:
        if not inp.content or not inp.content.strip():
            return False
        if inp.has_secrets:
            return False
        if inp.parse_status == ParseStatus.ERROR:
            return False
        return True

    @staticmethod
    def _prepare_content(inp: EmbeddingInput) -> str:
        content = inp.content
        if len(content.encode("utf-8")) > MAX_EMBEDDING_BYTES:
            lines = content.split("\n")
            shortened = "\n".join(lines[:MAX_OVERSIZE_LINES])
            return shortened
        return content

    @staticmethod
    def _validate_vector(vec: Any) -> list[float]:
        for v in vec:
            if isinstance(v, bool):
                raise EmbeddingEncoderError(
                    ErrorCode.EMBEDDING_FAILED,
                    "vector contains boolean value",
                )

        try:
            flat = [float(v) for v in vec]
        except (TypeError, ValueError):
            raise EmbeddingEncoderError(
                ErrorCode.EMBEDDING_FAILED,
                "vector not convertible to float",
            )

        if len(flat) != EXPECTED_DIMENSION:
            raise EmbeddingEncoderError(
                ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                f"vector length {len(flat)} != {EXPECTED_DIMENSION}",
            )

        for v in flat:
            if not isinstance(v, (int, float)):
                raise EmbeddingEncoderError(
                    ErrorCode.EMBEDDING_FAILED,
                    "vector contains non-numeric value",
                )

        import math
        for v in flat:
            if math.isnan(v):
                raise EmbeddingEncoderError(
                    ErrorCode.EMBEDDING_FAILED,
                    "vector contains NaN",
                )
            if math.isinf(v):
                raise EmbeddingEncoderError(
                    ErrorCode.EMBEDDING_FAILED,
                    "vector contains infinity",
                )

        return flat
