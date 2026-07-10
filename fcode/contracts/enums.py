"""Canonical enumerations — shared across all F Code modules."""

from enum import Enum, auto


class IndexPhase(str, Enum):
    SCAN = "scan"
    PARSE = "parse"
    GRAPH = "graph"
    CHUNK = "chunk"
    EMBED = "embed"
    PERSIST = "persist"


class IndexState(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    GRAPHING = "graphing"
    STORING = "storing"
    COMPLETE = "complete"
    ERROR = "error"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSED = "parsed"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


class FileType(str, Enum):
    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    DOC = "doc"


class SymbolType(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ROUTE = "route"
    VARIABLE = "variable"


class GraphNodeType(str, Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ROUTE = "route"
    IMPORT = "import"
    TEST = "test"


class GraphRelation(str, Enum):
    DEFINES = "defines"
    IMPORTS = "imports"
    INHERITS = "inherits"
    CALLS = "calls"
    TESTS = "tests"
    HANDLES_ROUTE = "handles_route"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class Confidence(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class ChunkType(str, Enum):
    FILE_SUMMARY = "file_summary"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    ROUTE = "route"
    TEST = "test"
    CONFIG = "config"
    README_SECTION = "readme_section"


class SearchMode(str, Enum):
    FTS5 = "fts5"
    LIKE_FALLBACK = "like_fallback"


class DiagnosticSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


class SupportedSetupAgent(str, Enum):
    CLI = "cli"
    STORAGE = "storage"
    SCANNER = "scanner"
    PARSER = "parser"
    GRAPH = "graph"
    CHUNKING = "chunking"
    EMBEDDINGS = "embeddings"
    RETRIEVAL = "retrieval"
    DASHBOARD = "dashboard"
    MCP = "mcp"
    TESTS = "tests"
    REPORTS = "reports"
