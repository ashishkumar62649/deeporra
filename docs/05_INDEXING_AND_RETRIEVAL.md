# 05_INDEXING_AND_RETRIEVAL.md — F Code Indexing and Retrieval Specification

## 1. Indexing Overview

Indexing is the process of scanning a repository, parsing code, creating chunks, generating embeddings, building the code graph, and storing everything locally.

```
repo_path → scan → parse → chunk → embed → graph → store → .fcode/
```

## 1a. Indexing State Machine

The indexing pipeline is governed by a pure state machine in `fcode/indexing/state_machine.py`.
It performs no I/O and knows nothing about the repository path.

**Current-build scope (WP5 Step 2 + Step 3):** Step 2 (`IndexService.build_through_chunking`)
validates the repository path and config, calls the scanner once, iterates parser candidates
with recoverable-error handling, and calls the chunker once. Step 3 (`IndexService.build_through_graphing`)
extends the pipeline through embedding (input construction + encoder call) and graph extraction
(graph builder call). Results remain in memory. Persistence, persistent replacement, `run_index`,
status services, and CLI activation are deferred to later WP5 steps.

### State progression

```
pending
→ scanning
→ parsing
→ chunking
→ embedding
→ graphing
→ storing
→ complete
```

Error is allowed from every non-terminal state.

### Phase mapping

| State | phase (active) |
|---|---|
| PENDING | None |
| SCANNING | SCAN |
| PARSING | PARSE |
| CHUNKING | CHUNK |
| EMBEDDING | EMBED |
| GRAPHING | GRAPH |
| STORING | PERSIST |
| COMPLETE | PERSIST |

### Completed-phase mapping

| Current state | completed_phase |
|---|---|
| PENDING | None |
| SCANNING | None |
| PARSING | SCAN |
| CHUNKING | PARSE |
| EMBEDDING | CHUNK |
| GRAPHING | EMBED |
| STORING | GRAPH |
| COMPLETE | PERSIST |

When transitioning to ERROR, the last completed phase and last active phase are preserved.

### Phase A / B / C boundaries

- **Phase A (preflight):** PENDING
- **Phase B (in-memory build):** SCANNING through GRAPHING
- **Phase C (persistent replacement):** STORING, COMPLETE; ERROR after STORING began

The `persistent_replacement_started` flag is `False` for PENDING through GRAPHING,
becomes `True` when STORING begins, and stays `True` through COMPLETE and
ERROR-from-STORING. This flag distinguishes failures before and after
destructive replacement began.

### State-machine purity

`state_machine.py` imports only `fcode.contracts.enums` and standard-library typing helpers.
It does not import scanner, parser, chunker, embeddings, graph, storage, SQLite, Chroma,
CLI, config, network, subprocess, or filesystem modules.

**Data flow contracts:** See `03_SYSTEM_ARCHITECTURE.md` Section 16 for the exact data structures passed between pipeline components (`RepoInput`, `ScannedFile`, `ParsedFile`, `CodeChunk`, `EmbeddingInput`, `EmbeddingRecord`, `GraphNodeInput`, `GraphEdgeInput`).

## 2. Repository Intake

**Input:** Local path or GitHub URL

**Steps:**
1. If GitHub URL: clone to temp directory, then index
2. If local path: validate it exists and is a directory
3. Check if already indexed (`.fcode/index.db` exists)
4. If already indexed: check for changes (content hash), offer reindex
5. Create `.fcode/` directory if not exists
6. Begin indexing pipeline

**Source:** `fcode/cli/index_cmd.py` + `fcode/storage/`

## 3. File Scanner

**Owner:** Scanner/Parser Agent
**File:** `fcode/scanner/file_scanner.py`

**Input:** `RepoInput.repo_path` (absolute path string)

**Preconditions:**
- `repo_path` exists and is a directory
- `.fcode/config.json` has been loaded or created

**Processing:**

1. Walk directory tree recursively using `os.walk`.
2. For each entry: apply ignore rules (Section 4).
3. For each eligible file: check symlink status — skip all symlinks (see Section 4a).
4. For each eligible file: check size <= 1MB (1,048,576 bytes). Skip if larger, log warning, increment `warning_count`.
5. For each eligible file: detect binary via extension and content (null bytes in first 8KB). Skip binary files, log info.
6. For each eligible file: run secret detection (Section 5).
7. Skip `.fcode/` directory entirely.
8. Normalize all paths to repo-relative POSIX-style strings using `/`.
9. Sort eligible paths by `(path.casefold(), path)` for deterministic ordering.
10. For each eligible file, create `ScannedFile` record with all required fields.
11. Set `parse_status = 'pending'` for Python files, `parse_status = 'not_applicable'` for non-Python files.

**Output:** `list[ScannedFile]` in deterministic sorted order.

**Persistence:** Scanner does not write to SQLite or Chroma directly. It returns the list to the orchestrator.

**Deterministic ordering:** Files are always processed in the order returned by the sorted scan. This order is the same for identical repository contents.

**File-type classification:**
- `.py`, `.pyw` → `language='python'`, `file_type` determined by path: files under `test*` or named `test_*.py` → `file_type='test'`; files matching config patterns → `file_type='config'`; files matching doc patterns (`.md`, `.rst`, `.txt`) → `file_type='doc'`; all others → `file_type='source'`

**Error behavior:**
- Repository path not found: raise `RepositoryNotFoundError` (fatal, exit code 2)
- Permission denied on directory: skip directory, log warning, continue
- Unreadable file: skip file, log warning, increment `warning_count`

**Cleanup:** No cleanup needed — scanner is read-only.

## 4. Ignore Rules

**Owner:** Scanner/Parser Agent
**File:** `fcode/scanner/ignore_rules.py`

F Code respects:
- `.gitignore` patterns (parse and apply)
- `.fcodeignore` patterns (if exists)
- Hardcoded ignores: `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `venv/`, `.env`, `.env.*`, `*.pyc`, `*.pyo`, `.fcode/`

**Implementation:** Parse `.gitignore` using a simple pattern matcher (no external dependency). Apply patterns relative to the directory containing the ignore file.

### 4a. Symlink Rules

The current build NEVER follows symlinks:

- Skip symlinked files (detected via `os.path.islink()`).
- Skip symlinked directories (do not recurse into them).
- Do not resolve symlinks to inspect external content.
- Log one sanitized warning per skipped symlink (include repo-relative path).
- Symlinks do not count toward indexed file totals, file count limits, or total size limits.
- A symlink pointing inside the repository is still skipped.
- A symlink pointing outside the repository is still skipped.
- No target-repository code is executed during symlink handling.

**Error behavior:**
- Symlink detected: skip, log warning, increment `warning_count`, continue.

**Source:** `fcode/scanner/ignore_rules.py` and `fcode/scanner/file_scanner.py`

## 5. Secret Handling

**Detection:**
1. Files named `.env`, `.env.*`, `.env.local`, `.env.production` → skip entirely (no `files` row, no chunk, no vector, not counted toward repository limits)
2. Files containing patterns: `API_KEY=`, `SECRET=`, `TOKEN=`, `PASSWORD=`, `PRIVATE_KEY` → flag as `has_secrets = 1`
3. Files containing PEM-encoded keys → flag as `has_secrets = 1`

**Behavior:**
- `.env` family files: skip completely, create no `files` row, create no chunk, create no vector, do not count toward repository limits
- Secret-bearing eligible source or config file: create a `files` row, set `has_secrets = true`, count toward repository limits, sanitize or redact sensitive values before any chunk content is created, do not store unredacted secret content in SQLite, do not send unredacted secret content to the embedding model, do not store unredacted secret content in Chroma, increment warning count with `file_secret_detected`
- Redacted content replaced with `[REDACTED]`
- Reports never include secret content
- Indexing may still complete with warnings

**Source:** `fcode/scanner/secret_detector.py`

## 6. Python Parser

**Owner:** Scanner/Parser Agent
**File:** `fcode/parser/python_ast.py`

**Current build: Python `ast` only.** Tree-sitter is NOT used in the first implementation slice.

**Input:** `ScannedFile` (absolute_path, file_id)

**Preconditions:**
- File exists and is readable
- File extension is `.py` or `.pyw`
- `parse_status` is `pending` on the file record

**Processing:**

1. Read file content as UTF-8.
2. Parse with `ast.parse(content)`.
3. If `SyntaxError` or `IndentationError`:
   - Set `parse_status = 'error'`
   - Set `parse_error = sanitized error message` (max 500 chars, no absolute paths, no secret content)
   - Create no symbols, no imports, no routes for this file
   - Create no symbol-based chunks for this file
   - Create a file_summary chunk only if the file has readable content (first 20 lines as raw text, with `chunk_type='file_summary'`)
   - Increment `warning_count`
   - Return `ParsedFile` with empty symbols/imports/routes lists
4. Walk AST tree.
5. Call `symbol_extractor.extract_symbols(tree, file_id)`.
6. Call `import_extractor.extract_imports(tree, file_id)`.
7. Call `route_detector.detect_routes(tree, file_id)`.
8. Set `parse_status = 'parsed'`.
9. Return `ParsedFile` with all fields populated.

**Output:** `ParsedFile`

**Error behavior:**
- Syntax error: recoverable. File gets `parse_status='error'`, indexing continues.
- UTF-8 decode error: treat as syntax error (same recovery path).
- Other I/O error: treat as syntax error (same recovery path).

**No tree-sitter usage:** Python `ast` is the only parser. No agent may introduce tree-sitter parsing into the first slice without a documentation change. Tree-sitter is reserved for later parser expansion (multi-language support).

**Source:** `fcode/parser/python_ast.py`

## 7. Symbol Extraction

**Owner:** Scanner/Parser Agent
**File:** `fcode/parser/symbol_extractor.py`

**Input:** Python AST (`ast.Module`), `file_id` (UUID)

**Output:** `list[ParsedSymbol]`

**Processing:**

Walk AST nodes and extract symbols in the following order:

1. For `ast.FunctionDef` and `ast.AsyncFunctionDef` at module level:
   - `symbol_type = 'function'`
   - Extract `name`, `qualified_name` (format: `module.function`), `start_line`, `end_line`, `signature`, `docstring` (`ast.get_docstring(node)`)
   - Set `parent_symbol_id = NULL`

2. For `ast.ClassDef` at module level:
   - `symbol_type = 'class'`
   - Extract `name`, `qualified_name` (format: `module.Class`), `start_line`, `end_line`, `signature` (class bases), `docstring`
   - Set `parent_symbol_id = NULL`

3. For `ast.FunctionDef` and `ast.AsyncFunctionDef` inside `ast.ClassDef`:
   - `symbol_type = 'method'`
   - Extract `name`, `qualified_name` (format: `module.Class.method`), `start_line`, `end_line`, `signature`, `docstring`
   - Set `parent_symbol_id` to the enclosing class's `symbol_id`

4. For `ast.Assign` at module level (target is a single name):
   - `symbol_type = 'variable'`
   - Extract `name`, `qualified_name`, `start_line`, `end_line`

**Duplicate symbols:** Do NOT overwrite. Every definition receives its own UUID and database row. Two functions with the same name in one file are stored separately. Two methods with the same name in different classes are stored separately. There is no uniqueness constraint on symbol name or qualified name in the schema. Each symbol is distinguished by: repository ID, file ID, start line, end line, UUID.

**Symbol ordering:** Within a file, symbols are ordered by `(start_line, end_line, name)`.

**Qualified name format:** `module.Class.method` or `module.function`. The module component is derived from the file's repo-relative path (e.g., `app/utils/validators.py` → module `app.utils.validators`).

**Error behavior:**
- Nested function (closure): extract as separate symbol with its own line range.
- Duplicate name at same level: both stored (no dedup).

**Source:** `fcode/parser/symbol_extractor.py`

## 8. Route Extraction

> **Scope note:** FastAPI is not used to build F Code. Route detection is only for indexed target repositories that use FastAPI. It belongs to the Python parser/indexing pipeline, not to F Code's own runtime architecture.

**Detection pattern:**
```python
# FastAPI routes in indexed repositories
@app.get("/path")
@app.post("/path")
@router.get("/path")
@router.post("/path")
@router.put("/path")
@router.delete("/path")
```

**Extraction:**
- HTTP method (get, post, put, delete, patch)
- Route path
- Handler function name
- File path and line number

**Route persistence:** Each detected route is persisted once as a symbol.

Map `ParsedRoute` to `symbols` exactly:

| Field | Value |
|-------|-------|
| id | route_id |
| symbol_type | `"route"` |
| name | `"<UPPERCASE_METHOD> <route_path>"` |
| qualified_name | handler qualified name |
| file_id | source file ID |
| start_line | decorator line |
| end_line | handler end line when known, otherwise start_line |
| signature | handler signature when known |
| docstring | handler docstring when known |
| metadata | JSON route metadata |

**Route metadata must contain:**
```json
{
  "http_method": "GET",
  "route_path": "/users",
  "handler_function": "module.handler",
  "decorators": ["app.get"]
}
```

**Graph builder must also create:**
- One route node
- One handler-function node if not already present
- One `handles_route` edge from the route node to the handler node

**Route node ID format:**
```
route:<uppercase_method>:<normalized_route_path>:<repo_relative_file_path>:<line_number>
```

**Route chunks:** Use the stored symbol and route metadata.

**Consistent output fields for MCP and dashboard:**
```
http_method
route_path
handler_function
file_path
line_number
```

**Source:** `fcode/parser/route_detector.py`

## 9. Import Extraction

`ParsedImport` is transient in the first build. There is no `imports` table.

**Exact flow:**
```
Python parser
→ ParsedImport
→ graph_builder.py
→ import graph node and imports edge
→ graph_store.py
```

**AST nodes:** `ast.Import`, `ast.ImportFrom`

**Extraction:**
- Module name (`module_name`)
- Imported names (`imported_names`, ordered list)
- Alias (nullable)
- Line number (1-based)

**Output:** List of `ParsedImport` per file, used for graph edge creation (imports edges). No `imports` table is persisted.

**Import edge metadata (persisted in `code_edges.metadata`):**
```json
{
  "module_name": "string",
  "imported_names": ["string"],
  "alias": "string or null",
  "line_number": 1
}
```

Rules:
- `module_name` is required
- `imported_names` is an ordered list
- `alias` is nullable
- `line_number` is 1-based
- `file_id` remains internal and is not returned publicly
- Multiple import statements must remain distinguishable by source file and line number
- Do not collapse two different import statements solely because they reference the same module

**MCP `get_file_context` output must use these field names:**
```text
module_name
imported_names
alias
line_number
```

**Do not use alternate field names:** `module`, `names`.

**Source:** `fcode/parser/import_extractor.py`

## 10. Code Graph Extraction

**Owner:** Scanner/Parser Agent (first phase)
**File:** `fcode/graph/graph_builder.py`

**Scope (first implementation slice):**

The graph builder in the first slice may ONLY:
- Convert files into file nodes
- Convert parsed symbols into symbol nodes (function, class, method, route, test)
- Convert imports into import nodes
- Connect routes to handler functions
- Connect tests to detected target symbols when evidence is directly extractable
- Produce `GraphNodeInput` and `GraphEdgeInput` records
- Apply confidence vocabulary: `EXTRACTED`, `INFERRED`, `AMBIGUOUS`

The graph builder in the first slice must NOT:
- Query SQLite
- Perform recursive graph traversal
- Calculate change impact
- Calculate risk
- Implement retrieval
- Implement NetworkX
- Create visualization logic

Graph traversal (`fcode/graph/graph_traverser.py`) and impact analysis (`fcode/graph/impact_analyzer.py`) are deferred to the Retrieval/Graph Agent in a later phase.

**Input:** `ParsedFile` list (all files in the repository)

**Output:** `list[GraphNodeInput]`, `list[GraphEdgeInput]`

### Variable Symbol Rules

Variable definitions are stored in `symbols` with `symbol_type = "variable"`. During the first slice:
- Variables do not become graph nodes
- No variable-related graph edges are produced
- Variables remain available to exact symbol lookup and later retrieval
- Graph builder processes functions, classes, methods, routes, files, imports, and tests only
- Do not add `variable` to `code_nodes.node_type` in the first slice

### Node Types

| Node Type | ID Format | Source |
|-----------|-----------|--------|
| file | `file:<repo_relative_path>` | Every scanned file |
| function | `function:<qualified_name>` | Every function symbol |
| class | `class:<qualified_name>` | Every class symbol |
| method | `method:<qualified_name>` | Every method symbol |
| route | `route:<http_method>:<normalized_route_path>:<repo_relative_file_path>:<line_number>` | Every detected route |
| import | `import:<module_name>` | Every unique import module |
| test | `test:<qualified_name>` | Every test function/class |

### First-Phase Edge Relations

| Relation | Source Node Type | Target Node Type | Extraction Rule | Direction | Confidence | Evidence Source |
|----------|-----------------|------------------|-----------------|-----------|------------|-----------------|
| `defines` | file | function, class, method, route, test | Symbol is defined in file | file → symbol | `EXTRACTED` | File contains symbol at documented line range |
| `imports` | file | import | `ast.Import` or `ast.ImportFrom` in file | file → import | `EXTRACTED` | AST import statement |
| `inherits` | class | class | `ast.ClassDef` bases contain a class name | child → parent | `EXTRACTED` | AST base class list |
| `calls` | function, method | function, method | `ast.Call` node references a function name in the same file | caller → callee | `EXTRACTED` | AST call node within function body |
| `tests` | test function/class | source function/class | Test file path convention (`test_*.py`) and test function name contains target function name | test → source | `INFERRED` | File naming convention + symbol name matching |
| `handles_route` | route | function | Route handler function name matches a function symbol | route → function | `EXTRACTED` | Route decorator handler function reference |

### Confidence Labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Explicitly found in source (import, direct call, inheritance, route handler) |
| `INFERRED` | Deduced from patterns (test-to-source by naming convention) |
| `AMBIGUOUS` | Uncertain relationship, flagged for review (not used in first-phase extraction) |

### Processing Order

1. Create file nodes first (one per scanned file).
2. Create symbol nodes (functions, classes, methods, routes, tests) in file order, then symbol order within file.
3. Create import nodes (deduplicated by module name).
4. Create `defines` edges (file → each symbol in that file).
5. Create `imports` edges (file → each import in that file).
6. Create `inherits` edges (class → base class, only if base class is defined in the same repository).
7. Create `calls` edges (function → called function, only if both are in the same file and the callee is a defined symbol).
8. Create `handles_route` edges (route → handler function).
9. Create `tests` edges (test → source, only when directly extractable from naming conventions).

**Error behavior:**
- If a target symbol for a `calls` edge is not found: skip that edge, log debug message.
- If a target symbol for a `inherits` edge is not found in the repository: skip that edge.
- Graph extraction never causes indexing failure.

**Source:** `fcode/graph/graph_builder.py`

## 11. Chunking Strategy

### Input Validation

Before any chunking, the chunker validates:
- Each `ScannedFile.file_id` is unique in the input
- Each `ParsedFile.file_id` is unique in the input
- Every parsed file has a matching scanned file
- Every Python file in scanned files has a matching parsed file (may be error status)

### Python

Files ending in `.py` or `.pyw` may produce the following chunk types:

| Chunk Type | Source | Size |
|------------|--------|------|
| file_summary | File docstring or first lines | 1 chunk per file |
| function | Function AST node | 1 chunk per function |
| class | Class AST node (with method summaries) | 1 chunk per class |
| method | Method AST node | 1 chunk per method |
| route | Route handler function | 1 chunk per route |
| test | Test function or class | 1 chunk per test |

**Chunk content:**
- For functions/methods: the full function body (including leading docstring and decorators).
- For classes: class signature line + docstring + method signatures (not full bodies). If no docstring, class body's first 20 lines or up to first method.
- For file summaries: file docstring + first 20 lines of content. If parser produced an error, first 20 lines of raw content.
- For routes: route decorator + handler function body.
- For tests: test function body.
- For files with `parse_status = 'error'`: no symbol chunks are produced; a single `file_summary` chunk is created from the first 20 lines of raw content.

**Symbol order within file:** Functions and methods are ordered by `(start_line, end_line)`.

### Documentation

Files ending in `.md` produce `readme_section` chunks split by Markdown headings (`# `, `## `, `### `, etc.). Files ending in `.rst` produce `readme_section` chunks split by RST section headings (underlined with `=`, `-`, `~`, etc.). They do not produce `file_summary` chunks.

Content before the first heading is treated as a single preamble section chunk.

### Configuration

Recognized configuration files produce `config` chunks:
- `*.json`, `*.toml`, `*.yaml`, `*.yml`, `*.ini`, `*.cfg`
- `requirements.txt`, `requirements-*.txt`, `pyproject.toml`
- `Makefile`, `Dockerfile`, `.gitignore`, `.fcodeignore`

Config files of 100 lines or fewer produce one chunk. Larger config files are split into deterministic consecutive blocks of 100 lines with no overlap.

### Generic Text Files

Other eligible text files:
- Receive a `files` row
- Use `parse_status = 'not_applicable'`
- Produce no chunks in the first slice
- Produce no vectors

### Chunk content source

The chunker uses `ScannedFile.safe_content` (already redacted by the scanner) as the content source, not the raw file content. If `safe_content` is empty, the chunker falls back to the raw file path.

### Chunk metadata

- repo_id (set by index_service at storage time)
- file_id
- symbol_id (if applicable)
- chunk_type
- start_line
- end_line
- content_hash
- language
- symbol_name
- file_path (repo-relative, POSIX separators, copied from scanned file at chunk creation)
- metadata (JSON), includes `has_secrets` and `parse_status`

**Source:** `fcode/chunking/chunker.py`

## 12. Embedding Strategy

**Owner:** Chunking/Embeddings Agent
**File:** `fcode/embeddings/encoder.py`

**Locked settings:**
- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Dimension: `384`
- Batch size: `100`
- Device: `cpu` (no GPU/CUDA in current build)

**Preconditions:**
- Model must already exist in the local cache (Sentence Transformers local-only loading mechanism — no hardcoded cache path inspected)
- Indexing never downloads the model; use device=`cpu` and prohibit downloads/remote calls
- `fcode doctor` reports whether the model is locally available
- Missing model is a fatal preflight error (`embedding_model_unavailable`, exit code 1)
- If local loading fails, do not begin persistent replacement, preserve the active previous index, do not automatically retry

**Processing:**

1. Load model once per indexing session: `SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')`
2. Collect all chunks eligible for embedding (non-empty content, `has_secrets != 1`).
3. For each eligible chunk:
   - If chunk content exceeds 100KB: use only the first 100 lines of content for embedding.
   - Encode content → 384-dim vector.
4. Batch encoding: process 100 chunks per batch.
5. For each produced vector: verify it contains exactly 384 numeric values.

**Embedding is NOT done for:**
- Chunks whose source was flagged with secrets (`has_secrets = 1`) — content is redacted before chunk creation
- Binary files (no `files` row created)
- Empty chunks (content is empty string)
- Chunks from files with `parse_status = 'error'` (no symbol chunks; file_summary chunks may exist)
- Generic text files that are not Python, Markdown, RST, or config (no chunks produced)

**Per-chunk failure behavior:**
- If encoding fails on a single chunk: record a warning, omit that chunk's vector, increment `warning_count`, continue to next chunk.
- The failed chunk is still stored in SQLite (content is present) but has no vector in Chroma.

**Whole-model failure behavior:**
- If the model cannot be loaded (not found, corrupted, dimension mismatch): raise a fatal exception. Indexing aborts. Error code: `embedding_model_unavailable`.
- If a produced vector has dimension other than 384: raise a fatal exception. Error code: `embedding_dimension_mismatch`.

**Completion rules:**
- The build may complete when at least one embeddable chunk succeeds, or the repository contains no embeddable chunks.
- If zero eligible chunks are successfully embedded while eligible chunks exist, the build fails with `embedding_all_chunks_failed`.
- A repository with no embeddable chunks (e.g., Markdown/config-only with no Python or all Python has parse errors) may complete with zero vectors only when there were genuinely no eligible chunks.
- Before marking complete, verify: `successful vectors = eligible embedding chunks - documented failed embedding chunks`.
- The build may complete with warnings if at least one searchable vector exists and all failed chunks are recorded in `warning_count`.

**No network calls:** Model loading and encoding never make network calls. The model must be pre-downloaded.

**No automatic retry:** Each chunk gets one encoding attempt. No retry on failure.

**Deterministic:** Same input content produces the same vector (model is deterministic for same input).

**Reindex after model change:** Full rebuild required. If the model name or dimension changes in config, the existing Chroma collection is deleted and recreated.

**Source:** `fcode/embeddings/encoder.py`

## 13. Chroma Storage Strategy

**Owner:** Storage Agent
**File:** `fcode/storage/chroma_store.py`

**Collection:** `code_chunks`

**Write method:** `upsert` (not `add`). Document ID = chunk UUID. This ensures idempotent writes and correct full-rebuild behavior.

**Repository separation:** All vectors include a `repo_id` metadata field. All queries and deletions filter by `repo_id`.

**Write process:**
1. For each `EmbeddingRecord`: call `collection.upsert(ids=[chunk_id], embeddings=[vector], metadatas=[metadata_dict])`.
2. Metadata dict must include: `repo_id`, `file_path`, `symbol_name`, `chunk_type`, `language`, `start_line`, `end_line`.

**Delete process (full rebuild):**
1. Before inserting new vectors: `collection.delete(where={'repo_id': repo_id})`.
2. This removes all previous vectors for the repository.

**Read process:**
1. Query Chroma with embedding vector and optional `where` filter.
2. Get top-k results with metadata.
3. Map `chunk_id` back to SQLite `chunks` table for full content.

**Failure behavior:**
- Chroma write failure after SQLite commit: run cleanup path (see `04_DATA_MODEL.md` Phase C failure).
- Chroma open failure: fatal preflight error, preserve previous index.

**Source:** `fcode/storage/chroma_store.py`

## 14. SQLite Metadata Strategy

**Owner:** Storage Agent
**File:** `fcode/storage/sqlite_store.py`

**Write process (full rebuild, inside one transaction):**
1. Delete previous rows for the repository: `chunks`, `symbols`, `files`, `code_nodes`, `code_edges`, `repo_reports`, `tool_call_logs`.
2. Insert new `repositories` record (or update existing).
3. Insert new `files` records with `parse_status` set by the parser.
4. Insert new `symbols` records.
5. Insert new `chunks` records.
6. Insert new `code_nodes` records.
7. Insert new `code_edges` records.
8. Update `index_status` with counts.
9. Commit the transaction.

**FTS5 tables:**
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    symbol_name,
    file_path,
    content='chunks',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name,
    qualified_name,
    content='symbols',
    content_rowid='rowid'
);
```

**FTS5 rebuild (after SQLite transaction commits):**
1. Drop existing FTS5 tables: `DROP TABLE IF EXISTS chunks_fts; DROP TABLE IF EXISTS symbols_fts;`
2. Recreate FTS5 tables with `content=` declarations.
3. Populate using rebuild command: `INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');`
4. Verify count: `SELECT COUNT(*) FROM chunks_fts` must equal `SELECT COUNT(*) FROM chunks WHERE repo_id = ?`.
5. If counts do not match: set `status = 'error'`, run cleanup.

**FTS5 unavailability:**
- Detect by attempting to create FTS5 table and catching `OperationalError`.
- If unavailable: log warning, set `active_search_mode = 'like_fallback'`, skip FTS5 creation.
- Keyword search falls back to `LIKE '%query%'` on `chunks.content` and `symbols.name`.

**FTS5 failure (other than unavailability):**
- Set `status = 'error'`, run cleanup path. Do not silently continue.

**Source:** `fcode/storage/sqlite_store.py` and `fcode/storage/fts_store.py`

### Graph Store

**Owner:** Storage Agent
**File:** `fcode/storage/graph_store.py`

**Responsibility:** Persist and read graph nodes and edges in SQLite tables `code_nodes` and `code_edges`.

**Write process (full rebuild, inside the same SQLite transaction as other tables):**
1. Insert new `code_nodes` records from `GraphNodeInput` list.
2. Insert new `code_edges` records from `GraphEdgeInput` list.

**Read process:**
1. Query nodes by `repo_id`, `node_type`, or `node_id`.
2. Query edges by `repo_id`, `source_node_id`, or `target_node_id`.
3. Recursive CTE for 2-hop traversal (deferred to `graph_traverser.py` in later phase).

**Source:** `fcode/storage/graph_store.py`

## 15. Keyword Search Strategy

**FTS5 query (when FTS5 is available):**
```sql
-- Search chunk content, map back to UUID
SELECT c.id, c.repo_id, c.file_id, c.symbol_id, c.chunk_type, c.content,
       c.start_line, c.end_line, c.language, c.symbol_name, f.path as file_path,
       chunks_fts.rank
FROM chunks_fts
JOIN chunks c ON c.rowid = chunks_fts.rowid
JOIN files f ON f.id = c.file_id
WHERE chunks_fts MATCH ? AND c.repo_id = ?
ORDER BY chunks_fts.rank
LIMIT ?;

-- Search symbol names, map back to UUID
SELECT s.id, s.repo_id, s.file_id, s.symbol_type, s.name, s.qualified_name,
       s.start_line, s.end_line, s.signature, f.path as file_path,
       symbols_fts.rank
FROM symbols_fts
JOIN symbols s ON s.rowid = symbols_fts.rowid
JOIN files f ON f.id = s.file_id
WHERE symbols_fts MATCH ? AND s.repo_id = ?
ORDER BY symbols_fts.rank
LIMIT ?;
```

**LIKE fallback (when FTS5 is unavailable):**
```sql
SELECT c.*, f.path as file_path
FROM chunks c
JOIN files f ON f.id = c.file_id
WHERE c.repo_id = ? AND c.content LIKE ?
LIMIT ?;

SELECT s.*, f.path as file_path
FROM symbols s
JOIN files f ON f.id = s.file_id
WHERE s.repo_id = ? AND s.name LIKE ?
LIMIT ?;
```

**LIKE fallback scoring:**
```
keyword_score =
  1.0 if exact phrase match
  0.7 if all query tokens match
  0.4 if some query tokens match
  0.0 otherwise
```

**Source:** `fcode/storage/fts_store.py`

## 16. Graph Traversal Strategy

**Primary method:** SQLite graph traversal. Direct relationship lookups use normal SQL queries. 2-hop traversal uses SQL recursive CTE.

**Note:** In-memory graph traversal is allowed only in tests, debugging utilities, or very small helper functions. In-memory graph traversal must not become the primary runtime path.

**SQL recursive CTE for related files (2-hop traversal):**
```sql
-- Find all files connected to a target within 2 hops
WITH RECURSIVE connected AS (
    -- Direct connections
    SELECT target_node_id as node_id, 1 as depth
    FROM code_edges
    WHERE source_node_id = ? AND relation IN ('defines', 'imports', 'inherits', 'calls', 'tests', 'handles_route')
    UNION
    -- Second hop
    SELECT e.target_node_id, c.depth + 1
    FROM code_edges e
    JOIN connected c ON e.source_node_id = c.node_id
    WHERE c.depth < 2
)
SELECT DISTINCT node_id FROM connected;
```

**Source:** `fcode/graph/graph_traverser.py`

## 17. Hybrid Retrieval Strategy

**When a query arrives:**

1. **Semantic search:** Encode query → Chroma search → top 10 chunks
2. **Keyword search:** FTS5 match on query terms → top 10 chunks
3. **Symbol lookup:** Exact match on query as symbol name → symbol + file
4. **Metadata filter:** Apply language, file_type, path filters
5. **Graph expansion:** For each top result, find related files via graph
6. **Combine:** Merge all results, deduplicate, rank by relevance

**Source:** `fcode/retrieval/hybrid_ranker.py`

## 18. Retrieval Ranking

**Ranking factors:**
1. Semantic similarity score (from Chroma, normalized 0-1)
2. Keyword match score (from FTS5, normalized 0-1)
3. Symbol exact match bonus (binary: 1.0 if exact, 0.0 otherwise)
4. Graph connectivity (count of graph edges, normalized by max in result set)
5. File type relevance (source: 1.0, test: 0.8, config: 0.5, doc: 0.3)
6. Recency (if multiple indexes, prefer latest)

**Weights:**
| Factor | Weight |
|--------|--------|
| Semantic similarity | 0.40 |
| Symbol exact match | 0.25 |
| Keyword match | 0.15 |
| Graph connectivity | 0.15 |
| File type relevance | 0.05 |

**Final score:**
```
score = (semantic × 0.40) + (symbol_bonus × 0.25) + (keyword × 0.15) + (graph × 0.15) + (file_type × 0.05)
```

**Normalization:**

All scores must be clamped to `0.0` to `1.0`. Missing signals score `0.0`. No negative scores. No scores above `1.0`. Returned results must include component scores.

### Semantic score
- Comes from vector similarity.
- Must be normalized to `0.0` to `1.0`.
- If the vector backend returns distance instead of similarity, convert with: `semantic_score = 1.0 - normalized_distance`
- Clamp to `0.0` to `1.0`.
- Missing semantic result = `0.0`.

### Keyword score (FTS5)
- FTS5 rank values are negative; lower (more negative) rank means better match.
- Convert: `keyword_score = 1.0 / (1.0 + abs(fts_rank))`
- Clamp to `0.0` to `1.0`.
- If no FTS5 result exists, `keyword_score = 0.0`.

### Keyword score (LIKE fallback, if FTS5 unavailable)
```
keyword_score =
  1.0 if exact phrase match
  0.7 if all query tokens match
  0.4 if some query tokens match
  0.0 otherwise
```

### Symbol score
```
symbol_score =
  1.0 for exact symbol match
  0.8 for case-insensitive exact match
  0.6 for partial symbol match
  0.4 for file/path name match
  0.0 for no symbol/path match
```

### Graph score
```
graph_score =
  1.0 if directly connected to a top candidate
  0.7 if connected within 2 hops
  0.4 if same file/module as a top candidate
  0.0 if no graph relationship exists
```

No division by edge count is allowed in the current build unless explicitly added later.

### Metadata score
```
metadata_score =
  1.0 if file type and symbol type strongly match the query intent
  0.7 if either file type or symbol type matches
  0.4 if path suggests relevance
  0.0 otherwise
```

### Global rules
- All scores must be clamped to `0.0` to `1.0`.
- Missing signals score `0.0`.
- Do not allow negative scores.
- Do not allow scores above `1.0`.
- Returned results must include component scores.
- Final score uses the already-defined weighted formula.

**Thresholds:**
| Score Range | Label | Behavior |
|-------------|-------|----------|
| >= 0.55 | Strong match | Return as primary result |
| 0.35 - 0.54 | Weak match | Return with confidence warning |
| < 0.35 | No match | Exclude from results |

**Tie-breakers (when scores are within 0.02):**
1. Prefer exact symbol match over semantic match
2. Prefer source files over test files
3. Prefer shorter files (more focused)
4. Prefer files with more graph edges (more connected)

**Source:** `fcode/retrieval/hybrid_ranker.py`

## 19. Evidence Format

Every retrieval result must include:

```json
{
  "file_path": "app/utils/validators.py",
  "symbol_name": "validate_email",
  "symbol_type": "function",
  "start_line": 42,
  "end_line": 68,
  "content_preview": "def validate_email(email: str) -> bool:\n    ...",
  "confidence": "EXTRACTED",
  "relevance_score": 0.92,
  "retrieval_method": "semantic",
  "evidence_reason": "Function matches query 'email validation'"
}
```

**Source:** `fcode/retrieval/evidence.py`

## 20. Reindexing Rules

**Current build behavior:** `fcode index <repo_path>` always performs a full rebuild. No `--force` flag exists. No incremental reindexing exists.

**Full rebuild state machine:** See `04_DATA_MODEL.md` Section 22 for the complete three-phase rebuild (Phase A: Preflight, Phase B: Build in Memory, Phase C: Persistent Replacement).

**Summary of rebuild steps:**

1. **Phase A (Preflight):** Validate path, config, writable directories, model availability, repository limits. If preflight fails, preserve previous index.
2. **Phase B (Build in Memory):** Scan, parse, chunk, embed, graph. All records held in memory. If fatal error, preserve previous index, discard temporary records.
3. **Phase C (Persistent Replacement):** Delete old SQLite rows, insert new rows, commit transaction, delete old Chroma vectors, upsert new vectors, rebuild FTS5, verify counts, mark complete. If failure after SQLite commit, clean up and mark error. Previous index is NOT restored after Phase C begins.

**Content hashes:** Stored with files for change detection and stale index warnings. Content hashes do not affect the rebuild process in the current build (no incremental mode).

**Source:** `fcode/indexing/index_service.py` + `fcode/storage/`

## 21. Failure Handling

### Error and Warning Catalog

Every error and warning has a code, severity, and defined behavior.

| Code | Severity | Meaning | Persistent Replacement Started? | CLI Exit |
|------|----------|---------|--------------------------------|----------|
| `invalid_repo_path` | error | Path is missing or not a directory | No | 2 |
| `config_invalid` | error | Config cannot be validated | No | 2 |
| `permission_denied` | error | Required path cannot be read or written | No | 1 |
| `repository_limit_exceeded` | error | File count (>10,000) or total size (>50MB) exceeds limits | No | 1 |
| `embedding_model_unavailable` | error | Locked local model cannot be loaded offline | No (preflight) | 1 |
| `embedding_dimension_mismatch` | error | Vector dimension is not 384 | No | 1 |
| `embedding_all_chunks_failed` | error | Zero eligible chunks successfully embedded | No | 1 |
| `sqlite_failure` | error | SQLite operation failed | Yes if Phase C; No if Phase B | 1 |
| `chroma_failure` | error | Chroma operation failed | Yes if Phase C; No if Phase B | 1 |
| `fts_failure` | error | Required FTS population failed or count mismatch | Yes | 1 |
| `verification_failed` | error | Record counts do not match after Phase C | Yes | 1 |
| `parse_warning` | warning | One file could not be parsed (syntax error) | No fatal effect | 0 if build succeeds |
| `file_skipped` | warning | File skipped by size, type, permission, secret, or symlink rule | No fatal effect | 0 if build succeeds |
| `file_secret_detected` | warning | File contains secrets, content redacted for embedding | No fatal effect | 0 if build succeeds |
| `embedding_chunk_warning` | warning | Individual chunk could not be embedded | No fatal effect unless zero vectors | 0 or 1 per rules |

### Error Object

Every error and warning produced during indexing uses this structure:

```
code: str           # from the catalog above
message: str        # sanitized, max 500 chars, no secrets, no absolute paths
phase: str          # preflight, scanning, parsing, chunking, embedding, graphing, storing
recoverable: bool   # True for warnings, False for errors
repo_relative_path: str | None  # optional, the file that caused the issue
details: str | None             # optional, additional sanitized context
```

Rules:
- `repo_relative_path` is optional.
- Messages are sanitized: no secret values, no full stack traces in CLI output.
- Internal logs may record stack traces locally.
- No absolute target-repository paths in MCP output.
- Warning and error counts are included in final `index_status`.

### Per-Phase Failure Behavior

| Failure | Behavior |
|---------|----------|
| File cannot be parsed (syntax error) | Set `parse_status='error'`, log `parse_warning`, increment `warning_count`, continue |
| File contains secrets | Set `has_secrets=1`, skip embedding for that file's chunks, continue |
| File too large (>1MB) | Skip file, log `file_skipped`, continue |
| Binary file detected | Skip file, log `file_skipped`, continue |
| Symlink detected | Skip file/dir, log `file_skipped`, continue |
| Individual embedding fails | Log `embedding_chunk_warning`, increment `warning_count`, continue |
| All embeddings fail | Set `status='error'`, code `embedding_all_chunks_failed` |
| SQLite write fails (Phase B) | Abort, preserve previous index |
| SQLite write fails (Phase C after commit) | Run cleanup, set `status='error'` |
| Chroma write fails (Phase C after SQLite commit) | Run cleanup, set `status='error'` |
| FTS population fails | Set `status='error'`, code `fts_failure` |
| FTS count mismatch | Set `status='error'`, code `verification_failed` |
| Disk full | Set `status='error'`, code `sqlite_failure` or `chroma_failure` |

**Source:** `fcode/indexing/index_service.py`

## 22. Performance Limits

| Limit | Value | Behavior |
|-------|-------|----------|
| Max eligible files | 10,000 | If exceeded, abort during preflight with `repository_limit_exceeded` |
| Max individual file size | 1 MB (1,048,576 bytes) | Skip file, log `file_skipped` |
| Max total eligible content | 50 MB | If exceeded, abort during preflight with `repository_limit_exceeded` |
| Max chunks per repo | 50,000 | Advisory; no hard abort (Chana query performance degrades) |
| Embedding dimension | 384 | Fixed; mismatch is fatal (`embedding_dimension_mismatch`) |
| Max graph hops (retrieval) | 2 | Deferred to retrieval phase |
| Max stored error length | 500 chars | Truncate longer messages |
| Embedding batch size | 100 | Fixed in current build |

**Counting rules:**
- Ignored files (by `.gitignore`, hardcoded ignores, `.fcodeignore`) do not count.
- Symlinks do not count.
- Binary files do not count toward eligible file count or content size.
- `.env` family files do not count.
- Files larger than 1 MB (1,048,576 bytes) are skipped and reported as warnings; they do not count.
- Only eligible files count toward the 10,000-file and 52,428,800-byte limits.
- The eligibility rule does not depend on `parse_status`. `parse_status` is assigned after eligibility is established:
  - Python before parsing: `pending`
  - parsed Python: `parsed`
  - failed Python parse: `error`
  - non-Python: `not_applicable`

## 23. Deterministic Ordering

All scanning, parsing, chunking, and persistence follows deterministic ordering:

1. **File order:** Normalize paths to repo-relative POSIX-style strings. Sort by `(path.casefold(), path)`.
2. **Symbol order within file:** Sort by `(start_line, end_line, name)`.
3. **Import order within file:** Sort by `line_number`.
4. **Route order within file:** Sort by `line_number`.
5. **Chunk order within file:** Sort by `(start_line, chunk_type, chunk_id)`.
6. **Graph node order:** File nodes first (in file order), then symbol nodes (in file order, then symbol order).
7. **Graph edge order:** In the order extracted by the graph builder.

IDs remain UUIDs and are not expected to be identical across rebuilds. Record ordering and semantic output must be deterministic even when IDs differ.

**Repeated indexing test:** Two runs of `fcode index` on the same repository with identical content must produce identical chunk content, identical symbol records, identical graph structure, and identical embedding vectors (same model, same input). The only difference will be UUIDs and timestamps.
