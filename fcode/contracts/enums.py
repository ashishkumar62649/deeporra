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
    IDLE = "idle"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FileType(str, Enum):
    PYTHON = "python"
    JUPYTER = "jupyter"
    MARKDOWN = "markdown"
    YAML = "yaml"
    TOML = "toml"
    JSON = "json"
    CONFIG = "config"
    UNKNOWN = "unknown"


class SymbolType(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    IMPORT = "import"


class GraphNodeType(str, Enum):
    FILE = "file"
    SYMBOL = "symbol"
    CHUNK = "chunk"


class GraphRelation(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    DEFINES = "defines"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class Confidence(str, Enum):
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class ChunkType(str, Enum):
    CODE = "code"
    DOCSTRING = "docstring"
    COMMENT = "comment"
    MARKDOWN = "markdown"


class SearchMode(str, Enum):
    EXACT = "exact"
    KEYWORD = "keyword"
    VECTOR = "vector"
    HYBRID = "hybrid"


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
