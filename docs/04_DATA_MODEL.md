# 04_DATA_MODEL.md — F Code Data Model

## 1. Storage Overview

F Code uses two local storage systems:

- **SQLite** — structured metadata, graph relationships, keyword search (FTS5)
- **Chroma** — vector embeddings for semantic search

All storage lives in `.fcode/` inside the indexed repository.

## 2. Local Index Location

```
<repo_path>/
├── .fcode/
│   ├── index.db          # SQLite database
│   ├── chroma/           # Chroma persistent store
│   ├── config.json       # F Code configuration (see Section 22)
│   └── reports/          # Generated reports (wiki, etc.)
```

## 3. Repository Identity

Each indexed repository is identified by:
- Absolute path on disk (primary key for local use)
- Content hash of the repository root (for change detection)
- Index timestamp

## 3a. SQLite Connection Rules

Every SQLite connection must enable:
```sql
PRAGMA foreign_keys = ON;
```

This ensures all `ON DELETE CASCADE` and `ON DELETE SET NULL` foreign-key policies defined in the schema are enforced.

## 4. SQLite Role

SQLite stores:
- Repository metadata
- File metadata
- Symbol metadata
- Chunk content (the actual code/text for each chunk)
- Code graph nodes and edges
- Indexing status
- Tool call logs
- Keyword search indexes (FTS5)

SQLite does NOT store:
- Vector embeddings (Chroma handles this)
- Full file content (files are on disk)
- Generated reports (filesystem)

## 5. Chroma Role

Chroma stores:
- Vector embeddings for each code chunk
- Metadata associated with each vector (file path, symbol, chunk type)
- The collection is named `code_chunks`

Chroma does NOT store:
- File content (only vectors and metadata)
- Graph relationships (SQLite handles this)
- Configuration

## 6. File Metadata Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| path | TEXT | Relative path from repo root (POSIX `/` separators) |
| absolute_path | TEXT | Full path on disk |
| language | TEXT | Detected language: `python` or `NULL` |
| file_type | TEXT | One of: `source`, `test`, `config`, `doc` |
| size_bytes | INTEGER | File size in bytes |
| line_count | INTEGER | Number of lines (0 for empty files) |
| content_hash | TEXT | SHA256 hex digest of file content |
| has_secrets | BOOLEAN DEFAULT 0 | Whether secrets were detected |
| parse_status | TEXT NOT NULL DEFAULT 'not_applicable' | One of: `pending`, `parsed`, `error`, `not_applicable` |
| parse_error | TEXT | Sanitized error message (max 500 chars) if parse_status is `error`, otherwise NULL |
| indexed_at | TIMESTAMP | When this file was indexed |

**`parse_status` values:**
- `pending` — file is eligible but has not been parsed yet
- `parsed` — Python file parsed successfully
- `error` — Python file failed to parse (syntax error or unreadable)
- `not_applicable` — non-Python file not passed through Python parser

**Writers:** scanner (creates record with `pending` or `not_applicable`), parser (updates to `parsed` or `error`)
**Readers:** storage, retrieval, graph, dashboard

## 7. Symbol Metadata Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| file_id | TEXT | Foreign key to files |
| symbol_type | TEXT | One of: `function`, `class`, `method`, `route`, `variable`. CHECK constraint enforces these values. |
| name | TEXT | Symbol name |
| qualified_name | TEXT | Full qualified name (module.Class.method) |
| start_line | INTEGER | Start line number |
| end_line | INTEGER | End line number |
| signature | TEXT | Function/method signature |
| docstring | TEXT | Docstring if present |
| parent_symbol_id | TEXT | For methods: the class ID |
| metadata | TEXT | JSON blob for extra data |

**Writers:** parser, symbol_extractor
**Readers:** storage, retrieval, graph, mcp_server

## 8. Chunk Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| file_id | TEXT | Foreign key to files |
| symbol_id | TEXT | Foreign key to symbols (if applicable) |
| chunk_type | TEXT | file_summary, function, class, method, route, test, config, readme_section |
| content | TEXT | The actual code/text content |
| start_line | INTEGER | Start line |
| end_line | INTEGER | End line |
| content_hash | TEXT | SHA256 of content |
| language | TEXT | Programming language |
| symbol_name | TEXT | Symbol name if applicable |
| file_path | TEXT | Repo-relative path (POSIX `/` separators), populated from files.path at chunk creation |
| metadata | TEXT | JSON blob |

**Writers:** chunker
**Readers:** embeddings, retrieval, mcp_server, dashboard

## 9. Embedding Model

| Field | Type | Description |
|-------|------|-------------|
| model_name | TEXT | Locked: "sentence-transformers/all-MiniLM-L6-v2" |
| dimension | INTEGER | Locked: 384 |
| created_at | TIMESTAMP | When this model was first used |

If the embedding model changes, all vectors must be regenerated.

## 10. Graph Node Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| node_id | TEXT | Unique within repo (e.g., "function:validate_email") |
| label | TEXT | Human-readable name |
| node_type | TEXT | file, function, class, method, route, import, test |
| source_file | TEXT | File path |
| source_location | TEXT | e.g., "L42-L68" |
| confidence | TEXT | EXTRACTED, INFERRED, AMBIGUOUS |
| metadata | TEXT | JSON blob |

**Writers:** graph_builder
**Readers:** graph_traverser, impact_analyzer, retrieval, mcp_server

## 11. Graph Edge Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| source_node_id | TEXT | Node ID of source |
| target_node_id | TEXT | Node ID of target |
| relation | TEXT | defines, imports, inherits, calls, tests, handles_route |
| confidence | TEXT | EXTRACTED, INFERRED, AMBIGUOUS |
| source_file | TEXT | File where this edge was found |
| metadata | TEXT | JSON blob |

**Writers:** graph_builder
**Readers:** graph_traverser, impact_analyzer, retrieval, mcp_server

## 12. Query/Tool Call Log Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| tool_name | TEXT | MCP tool name |
| input_params | TEXT | JSON of input parameters |
| output_summary | TEXT | Brief summary of result |
| result_count | INTEGER | Number of results returned |
| latency_ms | INTEGER | Response time |
| created_at | TIMESTAMP | When the call was made |

**Writers:** mcp_server
**Readers:** dashboard, status

## 13. Report/Wiki Model

| Field | Type | Description |
|-------|------|-------------|
| id | TEXT PRIMARY KEY | UUID |
| repo_id | TEXT | Foreign key to repositories |
| report_type | TEXT | wiki, summary, impact |
| content | TEXT | Generated report content (markdown) |
| format | TEXT | markdown, json |
| created_at | TIMESTAMP | When generated |
| invalidated_at | TIMESTAMP | When invalidated (reindex) |

**Writers:** wiki_generator
**Readers:** dashboard

## 14. Status Model

| Field | Type | Description |
|-------|------|-------------|
| repo_id | TEXT PRIMARY KEY | Foreign key to repositories |
| status | TEXT NOT NULL DEFAULT 'pending' | One of: `pending`, `scanning`, `parsing`, `chunking`, `embedding`, `graphing`, `storing`, `complete`, `error` |
| total_files | INTEGER DEFAULT 0 | Files discovered (eligible only) |
| indexed_files | INTEGER DEFAULT 0 | Files processed successfully |
| total_symbols | INTEGER DEFAULT 0 | Symbols extracted |
| total_chunks | INTEGER DEFAULT 0 | Chunks created |
| total_graph_nodes | INTEGER DEFAULT 0 | Graph nodes created |
| total_edges | INTEGER DEFAULT 0 | Graph edges extracted |
| total_vectors | INTEGER NOT NULL DEFAULT 0 | Vectors stored in Chroma |
| error_count | INTEGER NOT NULL DEFAULT 0 | Fatal errors during indexing |
| warning_count | INTEGER DEFAULT 0 | Warnings during indexing (parse warnings, embedding failures, skipped files) |
| embedding_model | TEXT | Model used (e.g. `sentence-transformers/all-MiniLM-L6-v2`) |
| active_search_mode | TEXT | One of: `fts5`, `like_fallback`. Set after FTS creation attempt. |
| started_at | TIMESTAMP | When indexing started |
| completed_at | TIMESTAMP | When indexing completed |
| error_message | TEXT | Sanitized error message if status is `error` |

**Writers:** indexer (via `fcode/indexing/index_service.py`)
**Readers:** dashboard, mcp_server, CLI status command

## 15. SQLite Tables

```sql
CREATE TABLE repositories (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE files (
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
);

CREATE TABLE symbols (
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
);

CREATE TABLE chunks (
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
);

CREATE TABLE code_nodes (
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
);

-- No UNIQUE constraint on (repo_id, source_node_id, target_node_id, relation)
-- Multiple edges between the same source and target are permitted
-- when they represent different evidence locations.
CREATE TABLE code_edges (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN ('defines', 'imports', 'inherits', 'calls', 'tests', 'handles_route')),
    confidence TEXT DEFAULT 'EXTRACTED' CHECK(confidence IN ('EXTRACTED', 'INFERRED', 'AMBIGUOUS')),
    source_file TEXT,
    metadata TEXT
);
-- No foreign keys from code_edges.source_node_id or code_edges.target_node_id
-- to code_nodes.node_id. Those values use application validation because
-- the referenced key is composite: repo_id + node_id.

CREATE TABLE index_status (
    repo_id TEXT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'scanning', 'parsing', 'chunking', 'embedding', 'graphing', 'storing', 'complete', 'error')),
    total_files INTEGER DEFAULT 0,
    indexed_files INTEGER DEFAULT 0,
    total_symbols INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 0,
    total_graph_nodes INTEGER DEFAULT 0,
    total_edges INTEGER DEFAULT 0,
    total_vectors INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    embedding_model TEXT,
    active_search_mode TEXT CHECK(active_search_mode IN ('fts5', 'like_fallback')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE tool_call_logs (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    input_params TEXT,
    output_summary TEXT,
    result_count INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE repo_reports (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,
    content TEXT NOT NULL,
    format TEXT DEFAULT 'markdown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    invalidated_at TIMESTAMP
);

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Indexes
CREATE INDEX idx_files_repo ON files(repo_id);
CREATE INDEX idx_symbols_repo ON symbols(repo_id);
CREATE INDEX idx_symbols_name ON symbols(repo_id, name);
CREATE INDEX idx_symbols_file ON symbols(file_id);
CREATE INDEX idx_chunks_repo ON chunks(repo_id);
CREATE INDEX idx_chunks_symbol ON chunks(symbol_id);
CREATE INDEX idx_code_edges_source ON code_edges(repo_id, source_node_id);
CREATE INDEX idx_code_edges_target ON code_edges(repo_id, target_node_id);
CREATE INDEX idx_code_edges_relation ON code_edges(repo_id, relation);
CREATE INDEX idx_tool_logs_repo ON tool_call_logs(repo_id);
CREATE INDEX idx_reports_repo ON repo_reports(repo_id);
```

## 16. Chroma Collections

**Collection name:** `code_chunks`

**Write method:** `upsert` (not `add`). Document ID = chunk UUID. Duplicate chunk UUIDs replace existing vectors.

**Repository separation:** All vectors include a `repo_id` metadata field. All queries and deletions filter by `repo_id`.

**Vector metadata (all Chroma metadata must contain these exact keys):**
| Field | Type | Description |
|-------|------|-------------|
| chunk_id | TEXT | References chunks.id (Chroma document ID) |
| repo_id | TEXT | References repositories.id |
| file_path | TEXT | Relative file path (repo-relative, POSIX separators) |
| symbol_name | TEXT | Symbol name if applicable, otherwise empty string (nullable values use empty string, not null) |
| chunk_type | TEXT | One of: file_summary, function, class, method, route, test, config, readme_section |
| language | TEXT | Programming language or NULL |
| start_line | INTEGER | Start line |
| end_line | INTEGER | End line |

**Dimension:** 384 (fixed). Local persistent client only. No network activity.

## 17. Indexing Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Indexing not started |
| `scanning` | File discovery in progress |
| `parsing` | AST extraction in progress |
| `chunking` | Chunk creation in progress |
| `embedding` | Vector generation in progress |
| `graphing` | Graph extraction in progress |
| `storing` | Writing to SQLite/Chroma/FTS5 |
| `complete` | Indexing finished successfully |
| `error` | Indexing failed |

## 18. FTS5 Implementation

### External-Content FTS5 Tables

FTS5 tables use SQLite's implicit integer `rowid` for content linking. The `chunks` and `symbols` tables are normal SQLite tables (not `WITHOUT ROWID`). SQLite automatically maintains an internal integer `rowid` for each row.

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,
    symbol_name,
    file_path,
    content='chunks',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE symbols_fts USING fts5(
    name,
    qualified_name,
    content='symbols',
    content_rowid='rowid'
);
```

The `file_path` column in `chunks_fts` maps directly to the `file_path` column in the `chunks` table. The chunker populates `chunks.file_path` from `files.path` at chunk creation time.

### FTS5 Rowid-to-UUID Mapping

```
FTS5 result rowid
→ SELECT id FROM chunks WHERE rowid = <fts_rowid>
→ SELECT id FROM symbols WHERE rowid = <fts_rowid>
→ use the UUID id in all public contracts (StoredChunkRef, EvidenceItem, ToolResult)
```

The internal `rowid` is storage-only and must not appear in MCP, dashboard, or any public contract. The `rowid` is stable only for the current index generation (rebuilt on every full reindex).

### FTS5 Rebuild Behavior

During every full rebuild, after all content rows are inserted:

1. Delete the existing FTS5 virtual tables: `DROP TABLE IF EXISTS chunks_fts; DROP TABLE IF EXISTS symbols_fts;`
2. Recreate the FTS5 virtual tables with the `content=` and `content_rowid=` declarations.
3. Populate using the FTS5 `rebuild` command:
   ```sql
   INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');
   INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild');
   ```
4. Verify the count of searchable FTS rows matches the count of content rows:
   ```sql
   SELECT COUNT(*) FROM chunks_fts;
   SELECT COUNT(*) FROM chunks;
   ```
   These counts must match. If they do not, treat as `fts_failure`.

### FTS5 Rebuild Timing

FTS5 rebuild occurs after the SQLite content transaction commits, using the complete current content tables.

### FTS5 Row-Count Verification

FTS5 row-count verification occurs before status becomes `complete`:
```sql
SELECT COUNT(*) FROM chunks_fts;
SELECT COUNT(*) FROM symbols_fts;
```
These counts must match the corresponding content-table row counts for the repository. If they do not match, treat as `fts_failure`.

### FTS5 Unavailability

If SQLite is compiled without FTS5 support:

1. Log a warning: `"FTS5 not available, falling back to LIKE-based keyword search"`.
2. Set `index_status.active_search_mode = 'like_fallback'`.
3. Do not create FTS5 virtual tables.
4. Keyword search uses `LIKE '%query%'` on `chunks.content` and `symbols.name`.
5. The `like_fallback` scoring is defined in `05_INDEXING_AND_RETRIEVAL.md`.

### FTS5 Failure Behavior

- FTS5 unavailable: log warning, activate LIKE fallback, record one warning, allow completion.
- FTS5 creation failure (other than unavailability): use `fts_failure`, set `status = 'error'`, run Phase C cleanup. Do not silently continue with partially populated FTS.
- FTS5 rebuild count mismatch: set `status = 'error'`, run Phase C cleanup.
- The active search mode (`fts5` or `like_fallback`) must be visible in `index_status.active_search_mode` and in `fcode status` output.

## 19. Data Retention Rules

- All index data is stored locally in `.fcode/`
- Index data persists until user deletes `.fcode/` or runs `fcode index <repo_path>` (which performs a full rebuild)
- `fcode index` always performs a full rebuild. No `--force` flag exists in the current build.
- Tool call logs are retained indefinitely (local only)
- Reports are regenerated on demand or invalidated on reindex
- No data is sent to external services

## 20. Privacy and Secret Handling

- `.env` files are detected and excluded from indexing entirely
- Files containing API keys, tokens, or secrets are flagged with `has_secrets = 1`
- Secret content is never stored in chunks, nodes, or reports
- Secret lines in chunks are replaced with `[REDACTED]` at chunk creation time
- Chunk content is stored in SQLite (for embedding and retrieval); full file content is read from disk at query time
- Embeddings are local (Sentence Transformers on CPU), no API calls
- No target-repository code is executed during indexing (AST-only parsing)

## 21. Migration Rules

- Schema changes are applied via SQL migration scripts
- Migrations are stored in `fcode/storage/migrations/`
- Each migration has an up and down script
- Migrations are applied automatically on first use
- Version tracked in SQLite `schema_version` table

## 22. Active Index Status Semantics

The documentation clearly distinguishes:

- The currently active persisted index
- The indexing attempt currently running in the CLI process

The current build does not add an `index_attempts` history table.

### When an active complete index already exists

During Phase A and Phase B:
- Do not modify the active `index_status` row
- Keep its status as `complete`
- Keep its counts, model, timestamps, and search mode unchanged
- Display current attempt progress only through the running CLI process

If Phase A or Phase B fails:
- Preserve all previous SQLite rows
- Preserve all previous Chroma vectors
- Preserve all previous FTS data
- Preserve `index_status.status = "complete"`
- Return the new attempt's error through the CLI
- Do not make the old index unavailable

When Phase C begins:
- Set the active status to `storing`
- Set `started_at` to the current attempt's start time
- Set `completed_at = NULL`
- Begin destructive replacement according to the existing Phase C contract

If Phase C fails:
- The previous index is not restored
- Remove partial new content
- Set status to `error`
- Set `completed_at`
- Store a sanitized error message
- Leave the repository unavailable as a complete index until indexing succeeds again

### When no previous active index exists

After path, configuration, and storage-open validation succeeds:
- Create the repository row
- Create one `index_status` row
- Set `status = "pending"`
- Set `started_at`
- Set `completed_at = NULL`

Then update the status through: `pending`, `scanning`, `parsing`, `chunking`, `embedding`, `graphing`, `storing`, `complete`.

On fatal failure after the row exists:
- Set `status = "error"`
- Set `completed_at`
- Write the sanitized error message

On failures before the database can safely be opened:
- Create no repository or status row

### Status History

- Only the latest active status is persisted
- The first slice does not store historical attempts
- `tool_call_logs` must not be used as an indexing-attempt history substitute

## 23. Timestamp Behavior

Exact rules:
- `started_at` is the accepted attempt start time
- For an existing active index, the persisted `started_at` is not changed during Phase A or Phase B
- For an existing active index, the new attempt start time remains in memory until Phase C begins
- When Phase C begins, write the new `started_at`
- For a repository without an index, create `index_status.started_at` after basic path/config/storage validation
- `completed_at` is `NULL` while processing
- Set `completed_at` when status becomes `complete`
- Set `completed_at` when status becomes `error`
- A preflight failure that preserves an existing complete index does not alter its timestamps

## 24. Repository-Row Behavior

There is one `repositories` row per local repository path.
- `repositories.path` is unique
- Reindexing reuses the existing repository ID
- The indexer does not delete the repository row during a normal rebuild
- It updates `content_hash` and `indexed_at` after successful replacement
- It does not update `indexed_at` for a failed Phase A or Phase B attempt
- During Phase C failure, retain the repository row and update the existing `index_status` row to `error`
- The first slice does not retain status history

## 25. Rebuild State Machine

A full rebuild replaces the active index for a repository. The rebuild has three phases:

### Phase A — Preflight

Before deleting any existing index data:

1. Validate the repository path exists and is a directory
2. Validate `.fcode/config.json` exists and is valid
3. Verify `.fcode/` directory is writable
4. Verify SQLite can be opened at `.fcode/index.db`
5. Verify Chroma can be opened at `.fcode/chroma/`
6. Verify the embedding model is available in local cache using local-only loading (no hardcoded cache path)
7. Verify the configured model dimension is 384
8. Perform one read-only discovery scan; count eligible files and verify they do not exceed limits (10,000 files, 52,428,800 bytes total)
9. Verify required storage directories can be created

**If preflight fails:**
- Do not delete existing index data
- Do not modify SQLite repository data
- Do not modify Chroma repository vectors
- Do not modify `index_status` (keep prior status `complete` if it existed)
- Return error to CLI with appropriate error code
- Preserve the previous usable index

### Phase B — Build in Memory

Before replacing any persisted data:

1. Reuse the same `ScannedFile` collection from Phase A discovery (no second filesystem walk)
2. Parse files (produce `ParsedFile` list)
3. Create chunks (produce `CodeChunk` list)
4. Generate embeddings (produce `EmbeddingRecord` list)
5. Generate graph nodes and edges (produce `GraphNodeInput`, `GraphEdgeInput` lists)

Generated records are held in process memory or temporary internal structures.

**If a fatal error happens during Phase B:**
- Preserve the previous index (leave `index_status.status = 'complete'`)
- Discard all temporary records
- Return error to CLI
- Do not begin persistent replacement

**Recoverable per-file warnings** (parse errors, embedding failures) may continue according to the rules defined in `05_INDEXING_AND_RETRIEVAL.md`. Each warning increments `warning_count`.

### Phase C — Persistent Replacement

After Phase B succeeds completely:

1. Set `index_status.status = 'storing'` (this is the moment the active status row changes)
2. Write the new attempt's `started_at`
3. Set `completed_at = NULL`
4. Begin one SQLite transaction
5. Delete the previous SQLite rows for the repository (chunks, symbols, files, code_nodes, code_edges, repo_reports, tool_call_logs)
6. Insert the new repository record (or update existing)
7. Insert new file, symbol, chunk, graph node, and graph edge rows
8. Update `index_status` with counts
9. Commit the SQLite transaction
10. Delete previous Chroma vectors for the repository (`collection.delete(where={'repo_id': repo_id})`)
11. Upsert all new Chroma vectors using chunk UUIDs as document IDs
12. Rebuild FTS5 tables (after SQLite content transaction commits)
13. Verify record counts (see verification section below)
14. Update `index_status.status = 'complete'`, set `completed_at`, set `embedding_model`, set `active_search_mode`

### Verification Counts

Before marking the index complete, verify:

| Metric | Expected | Query |
|--------|----------|-------|
| Files stored | `total_files` from status | `SELECT COUNT(*) FROM files WHERE repo_id = ?` |
| Symbols stored | `total_symbols` from status | `SELECT COUNT(*) FROM symbols WHERE repo_id = ?` |
| Chunks stored | `total_chunks` from status | `SELECT COUNT(*) FROM chunks WHERE repo_id = ?` |
| Chroma vectors | successfully embedded chunks | Chroma collection count with `repo_id` filter |
| Graph nodes | `total_graph_nodes` from status | `SELECT COUNT(*) FROM code_nodes WHERE repo_id = ?` |
| Graph edges | `total_edges` from status | `SELECT COUNT(*) FROM code_edges WHERE repo_id = ?` |
| FTS chunks | same as chunks count | `SELECT COUNT(*) FROM chunks_fts` |
| FTS symbols | same as symbols count | `SELECT COUNT(*) FROM symbols_fts` |

**If counts do not match:**
- Mark `index_status.status = 'error'`
- Run the same cleanup path as Phase C failure
- Do not mark the index complete

### Phase C Failure After SQLite Commit

If Chroma writing, FTS population, verification, or final status update fails after the SQLite transaction has committed:

1. Delete all new Chroma vectors for the repository on a best-effort basis
2. Begin a new SQLite cleanup transaction
3. Delete the newly inserted files, symbols, chunks, graph nodes, graph edges, repo_reports, and searchable content for the repository
4. Retain the repository record
5. Update the existing `index_status.status = 'error'`
6. Set `index_status.completed_at` to current timestamp
7. Write a sanitized `error_message` (max 500 chars, no secrets, no stack traces)
8. Ensure the repository cannot be returned as a complete index
9. Require the user to run `fcode index <repo_path>` again

**The previous index is NOT restored after Phase C has begun.** This limitation is explicit. The destructive replacement in Phase C step 5 is irreversible.

## 26. Config File Schema

See `03_SYSTEM_ARCHITECTURE.md` Section 21 for the full `.fcode/config.json` schema definition. The config file stores index configuration, embedding model settings, storage paths, and privacy settings.
