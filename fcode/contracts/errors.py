"""Canonical error codes — F Code domain errors and MCP tool errors."""

from enum import Enum, auto


class ErrorCode(str, Enum):
    # Preflight
    REPOSITORY_LIMIT_EXCEEDED = "repository_limit_exceeded"
    INVALID_REPOSITORY_PATH = "invalid_repository_path"
    # Scan
    FILE_SKIPPED = "file_skipped"
    SCAN_FAILED = "scan_failed"
    # Parse
    PARSE_FAILED = "parse_failed"
    # Graph
    GRAPH_BUILD_FAILED = "graph_build_failed"
    # Embed
    EMBEDDING_FAILED = "embedding_failed"
    EMBEDDING_MODEL_UNAVAILABLE = "embedding_model_unavailable"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    EMBEDDING_ALL_CHUNKS_FAILED = "embedding_all_chunks_failed"
    EMBEDDING_CHUNK_WARNING = "embedding_chunk_warning"
    # Persist
    PERSIST_FAILED = "persist_failed"
    # General
    UNEXPECTED_ERROR = "unexpected_error"
    NOT_IMPLEMENTED = "not_implemented"


class McpErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    NO_INDEX = "no_index"
    INDEX_IN_PROGRESS = "index_in_progress"
    TOOL_NOT_FOUND = "tool_not_found"
