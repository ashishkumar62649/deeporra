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
    chunk_id: str
    content: str
    metadata: "EmbeddingMetadata"
    has_secrets: bool = False
    parse_status: ParseStatus = ParseStatus.PARSED


@dataclass
class GraphNodeInput:
    record_id: str = ""
    external_id: str = ""
    node_type: GraphNodeType = GraphNodeType.FILE
    label: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.EXTRACTED
    node_id: str = ""
    source_file: str = ""
    source_location: str = ""
    metadata: Optional[dict[str, Any]] = None


@dataclass
class GraphEdgeInput:
    record_id: str = ""
    source_external_id: str = ""
    target_external_id: str = ""
    relation: GraphRelation = GraphRelation.DEFINES
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.EXTRACTED
    source_node_id: str = ""
    target_node_id: str = ""
    source_file: str = ""
    source_location: str = ""
    metadata: Optional[dict[str, Any]] = None


# ── Metadata ────────────────────────────────────────────────────────────────


@dataclass
class EmbeddingMetadata:
    chunk_id: str
    file_path: str
    symbol_name: str
    chunk_type: ChunkType
    language: Optional[str] = None
    start_line: int = 0
    end_line: int = 0


# ── Scan results ────────────────────────────────────────────────────────────


@dataclass
class ScannedFile:
    file_path: str = ""
    file_type: FileType = FileType.SOURCE
    size_bytes: int = 0
    is_binary: bool = False
    file_id: str = ""
    absolute_path: str = ""
    language: Optional[str] = None
    has_secrets: bool = False
    content_hash: str = ""
    parse_status: ParseStatus = ParseStatus.NOT_APPLICABLE
    safe_content: str = ""
    line_count: int = 0


@dataclass
class SkippedFileDiagnostic:
    file_path: str
    reason: str
    details: str = ""
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING


@dataclass
class ScanResult:
    files: list[ScannedFile] = field(default_factory=list)
    skipped: list[SkippedFileDiagnostic] = field(default_factory=list)
    total_count: int = 0
    total_bytes: int = 0
    eligible_file_count: int = 0
    eligible_total_bytes: int = 0
    warnings: list[dict] = field(default_factory=list)
    warning_count: int = 0


# ── Parse results ───────────────────────────────────────────────────────────


@dataclass
class ParsedSymbol:
    name: str = ""
    symbol_type: SymbolType = SymbolType.FUNCTION
    start_line: int = 0
    end_line: int = 0
    parent: Optional[str] = None
    docstring: Optional[str] = None
    confidence: Confidence = Confidence.EXTRACTED
    symbol_id: str = ""
    file_id: str = ""
    qualified_name: str = ""
    signature: Optional[str] = None
    parent_symbol_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ParsedImport:
    module_name: str = ""
    imported_names: list[str] = field(default_factory=list)
    line_number: int = 0
    is_relative: bool = False
    confidence: Confidence = Confidence.EXTRACTED
    file_id: str = ""
    alias: Optional[str] = None


@dataclass
class ParsedRoute:
    route_id: str = ""
    file_id: str = ""
    method: HttpMethod = HttpMethod.GET
    route_path: str = ""
    handler_function: str = ""
    start_line: int = 0
    signature: Optional[str] = None
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.INFERRED
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ParsedFile:
    file_path: str = ""
    file_type: FileType = FileType.SOURCE
    status: ParseStatus = ParseStatus.PENDING
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    routes: list[ParsedRoute] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    file_id: str = ""
    docstring: Optional[str] = None
    line_count: int = 0
    parse_error: Optional[str] = None


# ── Graph results ───────────────────────────────────────────────────────────


@dataclass
class GraphBuildResult:
    node_count: int = 0
    edge_count: int = 0
    errors: list[str] = field(default_factory=list)
    nodes: list[GraphNodeInput] = field(default_factory=list)
    edges: list[GraphEdgeInput] = field(default_factory=list)


# ── Chunk and embedding results ─────────────────────────────────────────────


@dataclass
class CodeChunk:
    chunk_id: str
    file_id: str
    chunk_type: ChunkType
    content: str
    start_line: int
    end_line: int
    file_path: str
    language: Optional[str] = None
    symbol_id: Optional[str] = None
    symbol_name: Optional[str] = None
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingRecord:
    chunk_id: str
    vector: list[float]
    metadata: EmbeddingMetadata


@dataclass
class EmbeddingBatchResult:
    records: list[EmbeddingRecord] = field(default_factory=list)
    eligible_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
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
