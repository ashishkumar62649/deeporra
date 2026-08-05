"""Pure validation and warning-conversion helpers for the indexing pipeline.

Extracted from `IndexService` so the orchestrator stays readable. Each
function is stateless: given an in-memory pipeline artifact (and/or config)
it returns an optional `(IndexDiagnostic, message)` error or a list of
diagnostics. No storage, network, or subprocess access.
"""

import hashlib
import math
import os
from pathlib import Path
from typing import Optional, Sequence

from deeporra.contracts import (
    CodeChunk,
    DeepOrraConfig,
    DiagnosticSeverity,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingRecord,
    ErrorCode,
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    IndexDiagnostic,
    IndexPhase,
    ParseStatus,
    ParsedFile,
    ScanResult,
    ScannedFile,
)
from deeporra.embeddings import EXPECTED_DIMENSION


# ── Embedding helpers ─────────────────────────────────────────────────────


def extract_partial_result(exc: BaseException) -> Optional[EmbeddingBatchResult]:
    if hasattr(exc, "result") and isinstance(exc.result, EmbeddingBatchResult):
        return exc.result
    return None


def embedding_exception_to_diagnostic(exc: BaseException) -> IndexDiagnostic:
    code = ErrorCode.EMBEDDING_FAILED.value
    message = "Embedding generation failed unexpectedly."
    if hasattr(exc, "code") and isinstance(exc.code, ErrorCode):
        code = exc.code.value
        if exc.code == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE:
            message = "Local embedding model is unavailable."
        elif exc.code == ErrorCode.EMBEDDING_DIMENSION_MISMATCH:
            message = "Embedding vectors do not match the required dimension."
        elif exc.code == ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED:
            message = "All eligible chunks failed to embed."
    return IndexDiagnostic(
        code=code,
        message=message,
        phase=IndexPhase.EMBED,
        recoverable=False,
        severity=DiagnosticSeverity.ERROR,
    )


def convert_embedding_warnings(
    result: EmbeddingBatchResult,
) -> list[IndexDiagnostic]:
    result_warnings: list[IndexDiagnostic] = []
    seen_ids: set[str] = set()
    for w in getattr(result, "warnings", []):
        if not isinstance(w, dict):
            result_warnings.append(IndexDiagnostic(
                code=ErrorCode.EMBEDDING_CHUNK_WARNING.value,
                message="One or more eligible chunks could not be embedded.",
                phase=IndexPhase.EMBED,
                recoverable=True,
                severity=DiagnosticSeverity.WARNING,
            ))
            continue
        chunk_id = w.get("chunk_id", "")
        raw_code = w.get("code", "")
        safe_code = raw_code if isinstance(raw_code, str) and raw_code else ErrorCode.EMBEDDING_CHUNK_WARNING.value
        warn_msg = "One or more eligible chunks could not be embedded."
        safe_path: Optional[str] = None
        raw_path = w.get("repo_relative_path") or w.get("path") or w.get("file_path")
        if isinstance(raw_path, str) and raw_path:
            if (not raw_path.startswith("/")
                    and not raw_path.startswith("\\")
                    and ".." not in raw_path.split("/")):
                safe_path = raw_path.replace("\\", "/")
        if chunk_id and chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
        result_warnings.append(IndexDiagnostic(
            code=safe_code,
            message=warn_msg,
            phase=IndexPhase.EMBED,
            recoverable=True,
            severity=DiagnosticSeverity.WARNING,
            repo_relative_path=safe_path,
        ))
    if result.fail_count > 0 and not result_warnings:
        result_warnings.append(IndexDiagnostic(
            code=ErrorCode.EMBEDDING_CHUNK_WARNING.value,
            message="One or more eligible chunks could not be embedded.",
            phase=IndexPhase.EMBED,
            recoverable=True,
            severity=DiagnosticSeverity.WARNING,
        ))
    return result_warnings


def validate_embedding_result(
    result: EmbeddingBatchResult,
    inputs: list[EmbeddingInput],
) -> Optional[tuple[IndexDiagnostic, str]]:
    if not isinstance(result, EmbeddingBatchResult):
        d = IndexDiagnostic(
            code=ErrorCode.EMBEDDING_FAILED.value,
            message="Embedder returned an invalid result type.",
            phase=IndexPhase.EMBED,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    for field_name in ("eligible_count", "success_count", "fail_count", "skipped_count"):
        val = getattr(result, field_name, -1)
        if isinstance(val, bool) or not isinstance(val, int):
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message=f"Embedding result {field_name} is not an integer.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if val < 0:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message=f"Embedding result {field_name} is negative.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

    if result.success_count != len(result.records):
        d = IndexDiagnostic(
            code=ErrorCode.EMBEDDING_FAILED.value,
            message="Embedding success_count does not match records length.",
            phase=IndexPhase.EMBED,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.success_count + result.fail_count != result.eligible_count:
        d = IndexDiagnostic(
            code=ErrorCode.EMBEDDING_FAILED.value,
            message="Embedding count invariant: success + fail != eligible.",
            phase=IndexPhase.EMBED,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.eligible_count + result.skipped_count != len(inputs):
        d = IndexDiagnostic(
            code=ErrorCode.EMBEDDING_FAILED.value,
            message="Embedding count invariant: eligible + skipped != total inputs.",
            phase=IndexPhase.EMBED,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    input_ids = [inp.chunk_id for inp in inputs]
    seen_ids: set[str] = set()

    for rec in result.records:
        if not isinstance(rec, EmbeddingRecord):
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding result contains a non-EmbeddingRecord item.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not rec.chunk_id:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding record has an empty chunk_id.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if rec.chunk_id in seen_ids:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding records contain a duplicate chunk_id.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_ids.add(rec.chunk_id)

        if rec.chunk_id not in input_ids:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding record references an unknown chunk_id.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if rec.metadata.chunk_id != rec.chunk_id:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding record metadata chunk_id mismatch.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        # Order: check record order follows eligible input order
        eligible_inputs = [inp for inp in inputs if inp.chunk_id in seen_ids]
        for i, rec_ci in enumerate(r.chunk_id for r in result.records):
            if i < len(eligible_inputs) and rec_ci != eligible_inputs[i].chunk_id:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record order does not match input order.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

        # Vector validation
        vec = rec.vector
        if len(vec) != EXPECTED_DIMENSION:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value,
                message=f"Embedding vector length {len(vec)} != {EXPECTED_DIMENSION}.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        for v in vec:
            if isinstance(v, bool):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding vector contains a boolean value.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if not isinstance(v, (int, float)):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding vector contains a non-numeric value.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if math.isnan(v) or math.isinf(v):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding vector contains NaN or infinity.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

        # Metadata path safety
        md_path = rec.metadata.file_path
        if md_path:
            if md_path.startswith("/") or md_path.startswith("\\"):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record has an absolute file_path in metadata.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ".." in md_path.split("/"):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record has a traversal file_path in metadata.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if "\\" in md_path:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record has a backslash file_path in metadata.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

    return None


# ── Graph helpers ─────────────────────────────────────────────────────────


def validate_graph_result(
    result: GraphBuildResult,
) -> Optional[tuple[IndexDiagnostic, str]]:
    if not isinstance(result, GraphBuildResult):
        d = IndexDiagnostic(
            code="graph_failed",
            message="Graph builder returned an invalid result type.",
            phase=IndexPhase.GRAPH,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    nodes = result.nodes
    edges = result.edges

    if not isinstance(nodes, list):
        d = IndexDiagnostic(
            code="graph_failed",
            message="Graph nodes is not a list.",
            phase=IndexPhase.GRAPH,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if not isinstance(edges, list):
        d = IndexDiagnostic(
            code="graph_failed",
            message="Graph edges is not a list.",
            phase=IndexPhase.GRAPH,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    seen_node_ids: set[str] = set()
    seen_node_record_ids: set[str] = set()

    for node in nodes:
        if not isinstance(node, GraphNodeInput):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph node list contains a non-GraphNodeInput item.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not node.node_id:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph node has an empty node_id.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if node.node_id in seen_node_ids:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph contains duplicate node IDs.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_node_ids.add(node.node_id)

        if not node.record_id:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph node has an empty record_id.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if node.record_id in seen_node_record_ids:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph contains duplicate node record IDs.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_node_record_ids.add(node.record_id)

        if not node.node_type:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph node has an empty node_type.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        # Path safety
        sf = node.source_file
        if sf:
            if sf.startswith("/") or sf.startswith("\\"):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node has an absolute source_file.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ".." in sf.split("/"):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node source_file contains traversal.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if "\\" in sf:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node source_file contains backslash.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

    seen_edge_ids: set[str] = set()
    seen_canonical_edges: set[tuple[str, str, str, str, str]] = set()

    for edge in edges:
        if not isinstance(edge, GraphEdgeInput):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge list contains a non-GraphEdgeInput item.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not edge.record_id:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge has an empty record_id.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if edge.record_id in seen_edge_ids:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph contains duplicate edge record IDs.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_edge_ids.add(edge.record_id)

        canonical_edge = (
            edge.source_node_id or "",
            edge.target_node_id or "",
            edge.relation.value if edge.relation else "",
            edge.source_file or "",
            edge.source_location or "",
        )
        if canonical_edge in seen_canonical_edges:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph contains duplicate canonical edge tuples.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_canonical_edges.add(canonical_edge)

        if not edge.source_node_id:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge has an empty source_node_id.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not edge.target_node_id:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge has an empty target_node_id.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not edge.relation:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge has an empty relation.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        # Endpoint integrity — source and target must be known nodes
        if edge.source_node_id not in seen_node_ids:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge source_node_id does not reference a known node.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if edge.target_node_id not in seen_node_ids:
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edge target_node_id does not reference a known node.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        # Edge path safety
        esf = edge.source_file
        if esf:
            if esf.startswith("/") or esf.startswith("\\"):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge source_file is absolute.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ".." in esf.split("/"):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge source_file contains traversal.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if "\\" in esf:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge source_file contains backslash.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

    if result.node_count != len(nodes):
        d = IndexDiagnostic(
            code="graph_failed",
            message="Graph result node_count does not match nodes list length.",
            phase=IndexPhase.GRAPH,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.edge_count != len(edges):
        d = IndexDiagnostic(
            code="graph_failed",
            message="Graph result edge_count does not match edges list length.",
            phase=IndexPhase.GRAPH,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    return None


# ── Step 2 helpers ────────────────────────────────────────────────────────


def validate_config(
    config: DeepOrraConfig,
) -> Optional[tuple[IndexDiagnostic, str]]:
    path = config.repo_path
    if not path or not isinstance(path, str):
        d = IndexDiagnostic(
            code=ErrorCode.INVALID_REPOSITORY_PATH.value,
            message="Repository path is missing or is not a readable directory.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    p = Path(path)
    if not p.exists():
        d = IndexDiagnostic(
            code=ErrorCode.INVALID_REPOSITORY_PATH.value,
            message="Repository path is missing or is not a readable directory.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if not p.is_dir():
        d = IndexDiagnostic(
            code=ErrorCode.INVALID_REPOSITORY_PATH.value,
            message="Repository path is missing or is not a readable directory.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if not os.access(str(p), os.R_OK | os.X_OK):
        d = IndexDiagnostic(
            code="permission_denied",
            message="Repository path is not readable.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    max_files = config.max_files
    if isinstance(max_files, bool) or not isinstance(max_files, int):
        d = IndexDiagnostic(
            code="config_invalid",
            message="max_files must be a positive integer.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message
    if max_files <= 0:
        d = IndexDiagnostic(
            code="config_invalid",
            message="max_files must be a positive integer.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    max_bytes = config.max_size_bytes
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        d = IndexDiagnostic(
            code="config_invalid",
            message="max_size_bytes must be a positive integer.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message
    if max_bytes <= 0:
        d = IndexDiagnostic(
            code="config_invalid",
            message="max_size_bytes must be a positive integer.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    return None


def validate_scan_result(
    result: ScanResult,
    config: DeepOrraConfig,
) -> Optional[tuple[IndexDiagnostic, str]]:
    if not isinstance(result, ScanResult):
        d = IndexDiagnostic(
            code=ErrorCode.SCAN_FAILED.value,
            message="Scanner returned an invalid result type.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    files = result.files
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for sf in files:
        if not sf.file_id:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned a file without an ID.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if sf.file_id in seen_ids:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned duplicate file IDs.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_ids.add(sf.file_id)

        if not sf.file_path:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned a file without a path.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if sf.file_path.startswith("/") or sf.file_path.startswith("\\"):
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned an absolute file path.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if ".." in sf.file_path.split("/"):
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned a path with '..' traversal.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if "\\" in sf.file_path:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned a path with backslash separators.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if sf.file_path in seen_paths:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned duplicate file paths.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_paths.add(sf.file_path)

    ec = result.eligible_file_count
    if ec != len(files):
        d = IndexDiagnostic(
            code=ErrorCode.SCAN_FAILED.value,
            message="Scanner eligible_file_count does not match files length.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    tc = result.total_count
    if tc != len(files):
        d = IndexDiagnostic(
            code=ErrorCode.SCAN_FAILED.value,
            message="Scanner total_count does not match files length.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.eligible_file_count < 0:
        d = IndexDiagnostic(
            code=ErrorCode.SCAN_FAILED.value,
            message="Scanner eligible_file_count is negative.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.eligible_total_bytes < 0:
        d = IndexDiagnostic(
            code=ErrorCode.SCAN_FAILED.value,
            message="Scanner eligible_total_bytes is negative.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.eligible_file_count > config.max_files:
        d = IndexDiagnostic(
            code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
            message="Repository exceeds maximum file count.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    if result.eligible_total_bytes > config.max_size_bytes:
        d = IndexDiagnostic(
            code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
            message="Repository exceeds maximum content size.",
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    for sk in result.skipped:
        if sk.reason == "repository_limit_exceeded":
            d = IndexDiagnostic(
                code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
                message="Repository exceeds indexing limits.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

    return None


def convert_scanner_warnings(
    scan_result: ScanResult,
) -> list[IndexDiagnostic]:
    result: list[IndexDiagnostic] = []
    for w in scan_result.warnings:
        if not isinstance(w, dict):
            result.append(IndexDiagnostic(
                code=ErrorCode.FILE_SKIPPED.value,
                message="A file was skipped during scanning.",
                phase=IndexPhase.SCAN,
                recoverable=True,
                severity=DiagnosticSeverity.WARNING,
            ))
            continue
        code = w.get("code") or ErrorCode.FILE_SKIPPED.value
        if not isinstance(code, str):
            code = ErrorCode.FILE_SKIPPED.value
        msg = w.get("message") or "A file was skipped during scanning."
        if not isinstance(msg, str):
            msg = "A file was skipped during scanning."
        msg = msg[:500]
        raw_path = w.get("repo_relative_path") or w.get("path") or w.get("file_path")
        safe_path: Optional[str] = None
        if isinstance(raw_path, str) and raw_path:
            if (not raw_path.startswith("/")
                    and not raw_path.startswith("\\")
                    and ".." not in raw_path.split("/")):
                safe_path = raw_path.replace("\\", "/")
        result.append(IndexDiagnostic(
            code=code,
            message=msg,
            phase=IndexPhase.SCAN,
            recoverable=True,
            severity=DiagnosticSeverity.WARNING,
            repo_relative_path=safe_path,
        ))
    return result


def validate_parse_result(
    pf: ParsedFile,
    sf: ScannedFile,
) -> Optional[tuple[IndexDiagnostic, str]]:
    if not isinstance(pf, ParsedFile):
        d = IndexDiagnostic(
            code=ErrorCode.PARSE_FAILED.value,
            message="Parser returned an invalid result type.",
            phase=IndexPhase.PARSE,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message
    if pf.file_id != sf.file_id:
        d = IndexDiagnostic(
            code=ErrorCode.PARSE_FAILED.value,
            message="Parser returned mismatched file ID.",
            phase=IndexPhase.PARSE,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message
    if pf.file_path != sf.file_path:
        d = IndexDiagnostic(
            code=ErrorCode.PARSE_FAILED.value,
            message="Parser returned mismatched file path.",
            phase=IndexPhase.PARSE,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message
    if pf.status not in (ParseStatus.PARSED, ParseStatus.ERROR, ParseStatus.NOT_APPLICABLE):
        d = IndexDiagnostic(
            code=ErrorCode.PARSE_FAILED.value,
            message="Parser returned a file with PENDING status.",
            phase=IndexPhase.PARSE,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    seen_sym: set[str] = set()
    for sym in pf.symbols:
        if not sym.symbol_id:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned a symbol without an ID.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if sym.symbol_id in seen_sym:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned duplicate symbol IDs.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_sym.add(sym.symbol_id)

    seen_route: set[str] = set()
    for rt in pf.routes:
        if not rt.route_id:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned a route without an ID.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if rt.route_id in seen_route:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned duplicate route IDs.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_route.add(rt.route_id)

    return None


def validate_chunks(
    chunks: list[CodeChunk],
    scanned_files: Sequence[ScannedFile],
) -> Optional[tuple[IndexDiagnostic, str]]:
    if not isinstance(chunks, list):
        d = IndexDiagnostic(
            code="chunk_failed",
            message="Chunker returned an invalid result type.",
            phase=IndexPhase.CHUNK,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )
        return d, d.message

    scanned_ids = {sf.file_id for sf in scanned_files}
    scanned_paths = {sf.file_path for sf in scanned_files}
    seen_ids: set[str] = set()

    for ch in chunks:
        if not isinstance(ch, CodeChunk):
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a non-CodeChunk item.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not ch.chunk_id:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a chunk without an ID.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if ch.chunk_id in seen_ids:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned duplicate chunk IDs.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        seen_ids.add(ch.chunk_id)

        if ch.file_id not in scanned_ids:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker referenced unknown file ID.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if ch.file_path not in scanned_paths:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker referenced unknown file path.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        fp = ch.file_path
        if fp.startswith("/") or fp.startswith("\\"):
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned an absolute file path.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if ".." in fp.split("/"):
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a path with '..' traversal.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if "\\" in fp:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a path with backslash separators.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if ch.start_line < 1:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a chunk with invalid start_line.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if ch.end_line < ch.start_line:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a chunk with end_line < start_line.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not isinstance(ch.content, str) or not ch.content.strip():
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a chunk with empty content.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        expected_hash = hashlib.sha256(ch.content.encode("utf-8")).hexdigest()
        if ch.content_hash and ch.content_hash != expected_hash:
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned a chunk with incorrect content hash.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

    return None