"""Canonical data models — shared across all F Code modules."""

from dataclasses import dataclass, field
from typing import Any, Optional
from fcode.contracts.enums import (
    ChunkType,
    Confidence,
    DiagnosticSeverity,
    FileType,
    GraphNodeType,
    GraphRelation,
    HttpMethod,
    IndexPhase,
    IndexState,
    ParseStatus,
    SymbolType,
)


# ── Inputs ──────────────────────────────────────────────────────────────────


@dataclass
class RepoInput:
    repo_path: str
    max_files: int = 10000
    max_size_bytes: int = 52_428_800
    skip_hidden: bool = True
    skip_binary: bool = True


@dataclass
class EmbeddingInput:
    text: str
    metadata: "EmbeddingMetadata"


@dataclass
class GraphNodeInput:
    external_id: str
    node_type: GraphNodeType
    label: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.EXTRACTED


@dataclass
class GraphEdgeInput:
    source_external_id: str
    target_external_id: str
    relation: GraphRelation
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.EXTRACTED


# ── Metadata ────────────────────────────────────────────────────────────────


@dataclass
class EmbeddingMetadata:
    source_file: str
    chunk_id: str
    chunk_type: ChunkType
    start_line: int
    end_line: int


# ── Scan results ────────────────────────────────────────────────────────────


@dataclass
class ScannedFile:
    file_path: str
    file_type: FileType
    size_bytes: int
    is_binary: bool = False


@dataclass
class SkippedFileDiagnostic:
    file_path: str
    reason: str
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING


@dataclass
class ScanResult:
    files: list[ScannedFile] = field(default_factory=list)
    skipped: list[SkippedFileDiagnostic] = field(default_factory=list)
    total_count: int = 0
    total_bytes: int = 0


# ── Parse results ───────────────────────────────────────────────────────────


@dataclass
class ParsedSymbol:
    name: str
    symbol_type: SymbolType
    start_line: int
    end_line: int
    parent: Optional[str] = None
    docstring: Optional[str] = None
    confidence: Confidence = Confidence.EXTRACTED


@dataclass
class ParsedImport:
    module: str
    names: list[str]
    start_line: int
    is_relative: bool = False
    confidence: Confidence = Confidence.EXTRACTED


@dataclass
class ParsedRoute:
    method: HttpMethod
    path: str
    handler: str
    start_line: int
    confidence: Confidence = Confidence.INFERRED


@dataclass
class ParsedFile:
    file_path: str
    status: ParseStatus
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    routes: list[ParsedRoute] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Graph results ───────────────────────────────────────────────────────────


@dataclass
class GraphBuildResult:
    node_count: int = 0
    edge_count: int = 0
    errors: list[str] = field(default_factory=list)


# ── Chunk and embedding results ─────────────────────────────────────────────


@dataclass
class CodeChunk:
    chunk_id: str
    text: str
    chunk_type: ChunkType
    source_file: str
    start_line: int
    end_line: int
    embedding: Optional[list[float]] = None


@dataclass
class EmbeddingRecord:
    chunk_id: str
    vector: list[float]
    metadata: EmbeddingMetadata


@dataclass
class EmbeddingBatchResult:
    success_count: int = 0
    fail_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class StoredChunkRef:
    chunk_id: str
    source_file: str


# ── Index pipeline results ──────────────────────────────────────────────────


@dataclass
class IndexCounts:
    scanned: int = 0
    parsed: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    chunks: int = 0
    embedded: int = 0


@dataclass
class IndexRunResult:
    state: IndexState
    phase: IndexPhase
    counts: IndexCounts = field(default_factory=IndexCounts)
    errors: list[str] = field(default_factory=list)


@dataclass
class IndexDiagnostic:
    phase: IndexPhase
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING


@dataclass
class IndexStatusRecord:
    state: IndexState
    phase: Optional[IndexPhase] = None
    completed_phase: Optional[IndexPhase] = None
    counts: IndexCounts = field(default_factory=IndexCounts)
    total_vectors: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    message: Optional[str] = None


# ── Doctor results ──────────────────────────────────────────────────────────


@dataclass
class DoctorCheck:
    name: str
    passed: bool
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR


@dataclass
class DoctorResult:
    checks: list[DoctorCheck] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


# ── Retrieval results ───────────────────────────────────────────────────────


@dataclass
class EvidenceItem:
    file_path: str
    start_line: int
    end_line: int
    content: str
    chunk_id: str
    score: float = 0.0
    chunk_type: ChunkType = ChunkType.FILE_SUMMARY


@dataclass
class RetrievalCandidate:
    chunk_id: str
    score: float
    evidence: EvidenceItem


# ── Retrieval results ───────────────────────────────────────────────────────


@dataclass
class FCodeConfig:
    repo_path: str = "."
    db_path: str = "fcode_data/fcode.db"
    chroma_path: str = "fcode_data/chroma"
    fts_enabled: bool = True
    max_files: int = 10000
    max_size_bytes: int = 52_428_800
    chunk_size: int = 512
    chunk_overlap: int = 64
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    scan_hidden: bool = False
    log_level: str = "INFO"


# ── MCP tool contract models ────────────────────────────────────────────────


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None


@dataclass
class ToolError:
    code: str
    message: str
