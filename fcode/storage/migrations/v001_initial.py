"""Schema version 1 — initial F Code storage schema."""

SCHEMA_VERSION = 1
SCHEMA_DESCRIPTION = "Initial F Code storage schema"

DDL_STATEMENTS = [
    # repositories
    """CREATE TABLE IF NOT EXISTS repositories (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        content_hash TEXT,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    # files
    """CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        path TEXT NOT NULL,
        absolute_path TEXT NOT NULL,
        language TEXT,
        file_type TEXT CHECK(file_type IN ('source', 'test', 'config', 'doc')),
        size_bytes INTEGER,
        line_count INTEGER,
        content_hash TEXT,
        has_secrets BOOLEAN DEFAULT 0,
        parse_status TEXT NOT NULL DEFAULT 'not_applicable' CHECK(parse_status IN ('pending', 'parsed', 'error', 'not_applicable')),
        parse_error TEXT,
        indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(repo_id, path)
    )""",
    # symbols
    """CREATE TABLE IF NOT EXISTS symbols (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        symbol_type TEXT NOT NULL CHECK(symbol_type IN ('function', 'class', 'method', 'route', 'variable')),
        name TEXT NOT NULL,
        qualified_name TEXT,
        start_line INTEGER,
        end_line INTEGER,
        signature TEXT,
        docstring TEXT,
        parent_symbol_id TEXT REFERENCES symbols(id) ON DELETE SET NULL,
        metadata TEXT
    )""",
    # chunks
    """CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        symbol_id TEXT REFERENCES symbols(id) ON DELETE SET NULL,
        chunk_type TEXT NOT NULL CHECK(chunk_type IN ('file_summary', 'function', 'class', 'method', 'route', 'test', 'config', 'readme_section')),
        content TEXT NOT NULL,
        start_line INTEGER,
        end_line INTEGER,
        content_hash TEXT,
        language TEXT,
        symbol_name TEXT,
        file_path TEXT NOT NULL,
        metadata TEXT
    )""",
    # code_nodes
    """CREATE TABLE IF NOT EXISTS code_nodes (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        node_id TEXT NOT NULL,
        label TEXT NOT NULL,
        node_type TEXT NOT NULL CHECK(node_type IN ('file', 'function', 'class', 'method', 'route', 'import', 'test')),
        source_file TEXT NOT NULL,
        source_location TEXT,
        confidence TEXT DEFAULT 'EXTRACTED' CHECK(confidence IN ('EXTRACTED', 'INFERRED', 'AMBIGUOUS')),
        metadata TEXT,
        UNIQUE(repo_id, node_id)
    )""",
    # code_edges (no UNIQUE on source,target,relation — multiple edges allowed)
    """CREATE TABLE IF NOT EXISTS code_edges (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        relation TEXT NOT NULL CHECK(relation IN ('defines', 'imports', 'inherits', 'calls', 'tests', 'handles_route')),
        confidence TEXT DEFAULT 'EXTRACTED' CHECK(confidence IN ('EXTRACTED', 'INFERRED', 'AMBIGUOUS')),
        source_file TEXT,
        metadata TEXT
    )""",
    # index_status
    """CREATE TABLE IF NOT EXISTS index_status (
        repo_id TEXT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'scanning', 'parsing', 'chunking', 'embedding', 'graphing', 'storing', 'complete', 'error')),
        total_files INTEGER DEFAULT 0,
        indexed_files INTEGER DEFAULT 0,
        total_symbols INTEGER DEFAULT 0,
        total_chunks INTEGER DEFAULT 0,
        total_graph_nodes INTEGER DEFAULT 0,
        total_edges INTEGER DEFAULT 0,
        total_vectors INTEGER NOT NULL DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        embedding_model TEXT,
        active_search_mode TEXT CHECK(active_search_mode IN ('fts5', 'like_fallback')),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        error_message TEXT
    )""",
    # tool_call_logs
    """CREATE TABLE IF NOT EXISTS tool_call_logs (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        tool_name TEXT NOT NULL,
        input_params TEXT,
        output_summary TEXT,
        result_count INTEGER,
        latency_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    # repo_reports
    """CREATE TABLE IF NOT EXISTS repo_reports (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        report_type TEXT NOT NULL,
        content TEXT NOT NULL,
        format TEXT DEFAULT 'markdown',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        invalidated_at TIMESTAMP
    )""",
    # schema_version
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        description TEXT
    )""",
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_files_repo ON files(repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_repo ON symbols(repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(repo_id, name)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_repo ON chunks(repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks(symbol_id)",
    "CREATE INDEX IF NOT EXISTS idx_code_edges_source ON code_edges(repo_id, source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_code_edges_target ON code_edges(repo_id, target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_code_edges_relation ON code_edges(repo_id, relation)",
    "CREATE INDEX IF NOT EXISTS idx_tool_logs_repo ON tool_call_logs(repo_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_repo ON repo_reports(repo_id)",
]


def apply(conn):
    """Apply the version 1 schema to the given connection.
    
    Executes inside a transaction. Raises on failure.
    """
    for stmt in DDL_STATEMENTS:
        conn.execute(stmt)
    for stmt in INDEX_STATEMENTS:
        conn.execute(stmt)
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
        (SCHEMA_VERSION, SCHEMA_DESCRIPTION),
    )
