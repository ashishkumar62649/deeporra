"""Protocol interfaces — canonical contracts for all F Code modules.

Each feature module's public interface is defined here.
Storage, pipeline, and service modules depend on protocols, not concrete classes.
"""

from typing import Optional, Sequence
from typing_extensions import Protocol
from fcode.contracts.models import (
    CodeChunk,
    DoctorResult,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingRecord,
    FCodeConfig,
    GraphBuildResult,
    IndexCounts,
    IndexRunResult,
    IndexStatusRecord,
    ParsedFile,
    RepoInput,
    ScanResult,
    ScannedFile,
    StoredChunkRef,
)


class ScannerProtocol(Protocol):
    def scan(self, repo: RepoInput, config: FCodeConfig) -> ScanResult: ...


class PythonParserProtocol(Protocol):
    def parse(self, file: ScannedFile) -> ParsedFile: ...


class GraphBuilderProtocol(Protocol):
    def build(self, parsed_files: Sequence[ParsedFile]) -> GraphBuildResult: ...


class ChunkerProtocol(Protocol):
    def chunk(self, parsed_files: list[ParsedFile]) -> list[CodeChunk]: ...


class EmbeddingEncoderProtocol(Protocol):
    def encode(self, inputs: list[EmbeddingInput]) -> list[EmbeddingRecord]: ...


class SQLiteStoreProtocol(Protocol):
    def store_index_run(self, result: IndexRunResult) -> None: ...
    def get_index_status(self) -> Optional[IndexStatusRecord]: ...
    def store_file_records(self, records: list[dict]) -> None: ...
    def store_graph(self, nodes: list[dict], edges: list[dict]) -> None: ...
    def store_chunks(self, chunks: list[dict]) -> None: ...
    def reset(self) -> None: ...


class ChromaStoreProtocol(Protocol):
    def store_embeddings(self, records: list[EmbeddingRecord]) -> None: ...
    def reset(self) -> None: ...
    def count(self) -> int: ...


class FTSStoreProtocol(Protocol):
    def rebuild(self, chunks: list[CodeChunk]) -> None: ...
    def reset(self) -> None: ...


class GraphStoreProtocol(Protocol):
    def store_graph(self, nodes: list[dict], edges: list[dict]) -> None: ...
    def reset(self) -> None: ...


class IndexServiceProtocol(Protocol):
    def run_index(self, config: FCodeConfig) -> IndexRunResult: ...
    def get_status(self) -> IndexStatusRecord: ...
    def get_counts(self) -> IndexCounts: ...


class StatusServiceProtocol(Protocol):
    def get_status(self) -> IndexStatusRecord: ...
    def doctor(self) -> DoctorResult: ...
