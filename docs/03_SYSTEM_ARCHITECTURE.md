# 03_SYSTEM_ARCHITECTURE.md — F Code System Architecture

## 1. Architecture Summary

F Code is a local-first Python CLI package with three interfaces:
- **CLI** — primary entry point for indexing and management
- **MCP stdio server** — read-only tools for coding agents
- **Streamlit dashboard** — local UI for human inspection

All interfaces share the same local storage layer (SQLite + Chroma) and the same Python service modules.

## 2. Local-First Architecture

```
User's Laptop
├── fcode CLI ──────────────────> fcode modules ──────────> .fcode/ (local storage)
├── MCP stdio server ───────────> fcode modules ──────────> .fcode/ (local storage)
└── Streamlit dashboard ────────> fcode modules ──────────> .fcode/ (local storage)
                                              │
                                              v
                                    SQLite (metadata, graph, FTS5)
                                    Chroma (vectors)
```

No network calls during operation. No cloud services. No external APIs.

## 3. Main Runtime Modes

| Command | Mode | Description | First Slice |
|---------|------|-------------|-------------|
| `fcode index <repo_path>` | Indexing | Scan, parse, embed, build graph | Functional |
| `fcode status [repo_path]` | Status | Show index status and stats | Functional |
| `fcode dashboard` | Dashboard | Start Streamlit on localhost | Stub (exit 2) |
| `fcode mcp --repo <repo_path>` | MCP Server | Start MCP stdio server | Stub (exit 2) |
| `fcode doctor` | Diagnostics | Check dependencies and health | Functional |
| `fcode setup <agent> --repo <repo_path>` | Setup | Configure agent integration | Stub (exit 2) |

**First-slice stub behavior:** `dashboard`, `mcp`, and `setup` commands accept their documented arguments, perform no subprocess launch, perform no network operation, perform no file modification, print `"This command is not available in the first implementation slice."`, and exit with code `2`. Their CLI help text identifies them as deferred.

## 4. CLI Architecture

```
fcode CLI (Typer)
├── index command ──────> index_service (orchestrator)
│                          ├── scanner ──────> file discovery, ignore rules, secret detection
│                          ├── parser ───────> Python AST extraction, symbol extraction
│                          ├── graph ────────> code relationship extraction
│                          ├── chunking ─────> semantic chunk creation
│                          ├── embeddings ───> Sentence Transformers encoding
│                          └── storage ──────> SQLite + Chroma + FTS5 write
├── status command ─────> storage service (read-only)
├── dashboard command ──> stub (exit 2) in first slice
├── mcp command ────────> stub (exit 2) in first slice
├── doctor command ─────> utils/health check
└── setup command ──────> stub (exit 2) in first slice
```

The CLI is thin. It parses arguments and calls service modules. No business logic in CLI handlers.

**Pipeline orchestration:** The `fcode/indexing/index_service.py` module owns pipeline orchestration. It controls status transitions, executes cleanup rules, maps fatal errors to the error catalog, and contains no parser/storage/chunking algorithms.

## 5. Indexer Architecture

```
indexer service
├── scanner ──────> file discovery, ignore rules, secret detection
├── parser ───────> Python AST extraction, symbol extraction
├── chunking ─────> semantic chunk creation
├── embeddings ───> Sentence Transformers encoding
├── graph ────────> code relationship extraction
└── storage ──────> SQLite + Chroma write
```

Indexing is a pipeline: scan → parse → chunk → embed → build graph → store.

## 6. Storage Architecture

```
Storage Layer
├── SQLite
│   ├── repositories table
│   ├── files table
│   ├── symbols table
│   ├── chunks table
│   ├── code_nodes table
│   ├── code_edges table
│   ├── index_status table
│   ├── tool_call_logs table
│   └── FTS5 virtual tables (keyword search)
│
├── Chroma
│   └── code_chunks collection (vectors + metadata)
│
└── Filesystem
    └── .fcode/reports/ (generated reports)
```

## 7. Retrieval Architecture

```
Retrieval Layer
├── semantic search ──> Chroma vector query
├── keyword search ──> SQLite FTS5 query
├── symbol lookup ───> SQLite exact match
├── metadata filter ─> SQLite WHERE clauses
├── graph expansion ─> SQL recursive query (callers, callees, imports)
└── hybrid ranking ──> combine + rerank results
```

## 8. Code Graph Architecture

```
Code Graph (first implementation slice)
├── Nodes: file, function, class, method, route, import, test
├── Edges: defines, imports, inherits, calls, tests, handles_route
├── Confidence: EXTRACTED, INFERRED, AMBIGUOUS
├── Storage: SQLite tables (code_nodes, code_edges)
├── Extraction: Python ast module only (no tree-sitter in first slice)
└── Traversal: DEFERRED to later phase (graph_traverser.py, impact_analyzer.py)
```

**First-slice scope:** Graph extraction only. Graph traversal, hybrid graph retrieval, impact analysis, and change-risk analysis are deferred to the Retrieval/Graph Agent phase.

**Ownership:** `fcode/graph/graph_builder.py` is owned by the Scanner/Parser Agent. `fcode/graph/graph_traverser.py` and `fcode/graph/impact_analyzer.py` are owned by the Retrieval/Graph Agent (later phase).

## 9. MCP Server Architecture

```
MCP Server (stdio transport)
├── Tool dispatcher
│   ├── search_code ──────────> retrieval service
│   ├── find_symbol ──────────> storage service
│   ├── get_file_context ─────> storage service
│   ├── find_related_files ───> graph service
│   ├── check_existing_implementation ──> retrieval + graph
│   ├── plan_minimal_change ──> retrieval + graph + planner
│   ├── find_related_tests ──> storage + graph
│   └── explain_change_impact ──> graph service
│
├── Read-only enforcement
│   └── No write/edit/delete operations allowed
│
└── Logging
    └── tool_call_logs table
```

## 10. Dashboard Architecture

```
Streamlit Dashboard (localhost:8501)
├── Page 1: Connect Repository ──> indexer service
├── Page 2: Indexing Status ─────> storage service
├── Page 3: Repository Wiki ─────> storage + graph service
├── Page 4: Ask Repository ──────> retrieval service
└── Page 5: Agent Tools Preview ─> retrieval + graph services
```

Dashboard calls Python service modules directly. No FastAPI. No HTTP. No MCP tool wrappers.

## 11. LLM Usage Architecture

Current build does NOT require an LLM API for core functionality:
- Embeddings: local Sentence Transformers
- Code parsing: Python AST (no LLM)
- Graph extraction: AST-based (no LLM)
- Retrieval: vector + keyword + graph (no LLM)

Optional LLM usage (later):
- Enhanced code summarization
- Complex question answering
- Natural language to query translation

## 12. Security Architecture

```
Security Layers
├── Input validation ────> all user inputs sanitized
├── Secret detection ────> .env files, API keys, tokens redacted
├── Path validation ─────> no path traversal, no symlink attacks
├── Network isolation ───> no outbound calls during operation
├── Local-only server ──> MCP stdio only, dashboard localhost only
├── Read-only MCP tools ─> no file writes, no shell execution
└── No code upload ──────> repository stays on user's machine
```

## 13. Data Flow Diagrams

### Indexing Flow

```
User: fcode index /path/to/repo
  │
  v
Scanner: discover files, apply ignore rules, detect secrets
  │
  v
Parser: Python AST → extract symbols, imports, routes
  │
  v
Chunker: create semantic chunks (function, class, file summary)
  │
  v
Embedder: Sentence Transformers → vector per chunk
  │
  v
Graph builder: extract nodes and edges from AST
  │
  v
Storage: write SQLite tables + Chroma collection
  │
  v
Done: .fcode/ directory created with index
```

### MCP Tool Flow

```
Coding Agent: calls check_existing_implementation("email validation")
  │
  v
MCP Server: receives tool call via stdio
  │
  v
Retrieval: semantic search + keyword search + symbol lookup
  │
  v
Graph: check for existing related implementations
  │
  v
Response: file path, symbol name, line range, evidence
  │
  v
Coding Agent: decides to reuse existing code
```

### Dashboard Flow

```
User: opens localhost:8501
  │
  v
Streamlit: renders Connect Repository page
  │
  v
User: enters GitHub URL
  │
  v
Indexer: clones repo, runs indexing pipeline
  │
  v
Dashboard: shows Repository Wiki page
  │
  v
User: asks question "Where is auth handled?"
  │
  v
Retrieval: finds relevant files and symbols
  │
  v
Dashboard: shows evidence with file paths and line ranges
```

### Retrieval Flow

```
Query: "email validation function"
  │
  ├──> Semantic: Chroma vector search → top 10 chunks
  ├──> Keyword: SQLite FTS5 → top 10 matches
  └──> Symbol: SQLite exact match → "validate_email"
  │
  v
Combine: merge results, deduplicate
  │
  v
Graph expansion: for each top result, find related files via imports/calls
  │
  v
Filter: metadata (language, file type, path)
  │
  v
Rank: weighted combination of semantic, keyword, graph connectivity
  │
  v
Return: ranked evidence with file paths, symbols, line ranges
```

## 14. Module Boundaries

`fcode/indexing/index_service.py` is owned by the Integration Agent. It is the only module that controls:
- Phase order
- Phase progress
- Active-status transitions
- SQLite transaction initiation
- Chroma replacement initiation
- FTS rebuild initiation
- Verification counts
- Cleanup order
- Error mapping
- CLI result

### Storage module boundaries:
- `sqlite_store.py` accesses SQLite only.
- `chroma_store.py` accesses Chroma only.
- `graph_store.py` accesses graph tables in SQLite only.
- `fts_store.py` accesses FTS5/SQLite only.
- Storage modules do not call each other.
- Storage modules do not control the full pipeline.
- Parser, scanner, graph builder, chunker, and embedder do not call persistence modules directly.
- `index_service.py` calls each module through its public interface.

| Module | Responsibility | Depends On |
|--------|---------------|------------|
| `fcode/contracts/` | Shared enums, models, errors, interfaces (WP0) | None |
| `fcode/cli/` | CLI entry point, argument parsing | contracts + All services |
| `fcode/config/` | Configuration management | None |
| `fcode/indexing/` | Pipeline orchestration (Phase A, B, C) | All index services |
| `fcode/scanner/` | File discovery, ignore rules | None |
| `fcode/parser/` | Python AST extraction | None |
| `fcode/chunking/` | Semantic chunk creation | parser output |
| `fcode/embeddings/` | Sentence Transformers encoding | None |
| `fcode/storage/` | SQLite + Chroma operations | None |
| `fcode/retrieval/` | Hybrid search + ranking | storage, embeddings |
| `fcode/graph/` | Code graph extraction + traversal | parser output, storage |
| `fcode/mcp_server/` | MCP stdio server | retrieval, graph, storage |
| `fcode/dashboard/` | Streamlit UI | All services |
| `fcode/reports/` | Report generation | storage, graph |
| `fcode/utils/` | Shared utilities (owned by CLI/Config Agent; see ownership rules) | None |

## 15. Package/Folder Structure

```
fcode/
├── __init__.py          # Re-exports contracts
├── __main__.py          # CLI entry point
├── contracts/           # WP0 — Shared contracts package
│   ├── __init__.py
│   ├── enums.py         # Canonical enum types
│   ├── models.py        # Canonical data models
│   ├── errors.py        # Canonical error codes
│   └── interfaces.py    # Protocol interfaces
├── cli/
│   ├── __init__.py
│   ├── main.py          # Typer commands
│   ├── index_cmd.py     # fcode index
│   ├── status_cmd.py    # fcode status
│   ├── dashboard_cmd.py # fcode dashboard
│   ├── mcp_cmd.py       # fcode mcp
│   ├── doctor_cmd.py    # fcode doctor
│   └── setup_cmd.py     # fcode setup
├── config/
│   ├── __init__.py
│   ├── settings.py      # configuration management
│   └── defaults.py      # default values
├── scanner/
│   ├── __init__.py
│   ├── file_scanner.py  # file discovery
│   ├── ignore_rules.py  # .gitignore, .fcodeignore
│   └── secret_detector.py # .env, API keys
├── parser/
│   ├── __init__.py
│   ├── python_ast.py    # Python AST extraction
│   ├── symbol_extractor.py # functions, classes, methods
│   ├── import_extractor.py # import statements
│   └── route_detector.py  # FastAPI route detection for indexed repos only
├── chunking/
│   ├── __init__.py
│   └── chunker.py       # semantic chunk creation
├── embeddings/
│   ├── __init__.py
│   └── encoder.py       # Sentence Transformers
├── storage/
│   ├── __init__.py
│   ├── sqlite_store.py  # SQLite operations
│   ├── chroma_store.py  # Chroma operations
│   ├── graph_store.py   # code_nodes, code_edges
│   └── fts_store.py     # FTS5 keyword search
├── retrieval/
│   ├── __init__.py
│   ├── semantic_search.py  # vector search
│   ├── keyword_search.py   # FTS5 search
│   ├── symbol_lookup.py    # exact symbol match
│   ├── hybrid_ranker.py    # combine + rank
│   └── evidence.py         # evidence formatting
├── indexing/
│   ├── __init__.py
│   └── index_service.py    # pipeline orchestrator (Phase A, B, C)
├── graph/
│   ├── __init__.py
│   ├── graph_builder.py    # extract nodes/edges from AST
│   ├── graph_traverser.py  # SQL recursive queries
│   └── impact_analyzer.py  # change impact analysis
├── mcp_server/
│   ├── __init__.py
│   ├── server.py        # MCP stdio server
│   ├── tools.py         # tool definitions
│   └── handlers.py      # tool implementations
├── dashboard/
│   ├── __init__.py
│   ├── app.py           # Streamlit main
│   ├── pages/
│   │   ├── 1_connect.py
│   │   ├── 2_status.py
│   │   ├── 3_wiki.py
│   │   ├── 4_ask.py
│   │   └── 5_tools.py
│   └── components/
│       ├── evidence_card.py
│       └── file_viewer.py
├── reports/
│   ├── __init__.py
│   └── wiki_generator.py
└── utils/
    ├── __init__.py
    ├── hashing.py
    ├── path_utils.py
    └── health.py

tests/
├── unit/
├── integration/
├── fixtures/
└── golden/

docs/
├── 01_CONTEXT.md
├── 02_PRODUCT_SPEC.md
├── 03_SYSTEM_ARCHITECTURE.md
├── 04_DATA_MODEL.md
├── 05_INDEXING_AND_RETRIEVAL.md
├── 06_MCP_TOOLS_CONTRACT.md
├── 07_DASHBOARD_SPEC.md
├── 08_SCENARIOS_AND_ACCEPTANCE_TESTS.md
└── 09_AGENT_TASKS.md
```

## 16. Data Flow Contracts

All pipeline components communicate through these defined data structures. No component may invent fields outside these contracts without updating this document.

### Global Rules

- Parser output must not include embeddings.
- Chunker output must not write directly to Chroma.
- Embedder only receives `EmbeddingInput`, not raw repository files.
- Storage layer owns persistence.
- Retrieval layer reads from storage but does not mutate index data.
- MCP tools and dashboard call shared services; neither owns business logic.
- All file paths are repo-relative unless explicitly marked absolute.
- All line numbers are 1-based and inclusive.
- IDs must be stable within a single index version.

### Contract Definitions

| Object | Purpose | Producer | Consumer | Required Fields | Optional Fields | Notes |
|--------|---------|----------|----------|-----------------|-----------------|-------|
| `RepoInput` | Repository reference for indexing | CLI, Dashboard | Indexer | `repo_path` (absolute), `repo_url` (if GitHub) | `branch`, `commit_hash` | Path must be validated before indexing |
| `ScannedFile` | Discovered file with metadata | Scanner | Parser | `absolute_path`, `relative_path`, `size_bytes`, `language`, `is_binary`, `has_secrets` | `content_hash` | Excludes ignored/secret files |
| `ParsedFile` | Parsed file with symbols | Parser | Chunker, Graph Builder | `file_id`, `relative_path`, `symbols` (list of `ParsedSymbol`), `imports` (list of `ParsedImport`), `routes` (list of `ParsedRoute`) | `docstring`, `line_count` | No embeddings included |
| `ParsedSymbol` | Extracted symbol definition | Parser | Chunker, Graph Builder | `symbol_id`, `name`, `qualified_name`, `symbol_type`, `start_line`, `end_line`, `file_id` | `signature`, `docstring`, `parent_symbol_id` | Types: function, class, method, route, variable |
| `ParsedImport` | Extracted import statement | Parser | Graph Builder | `module_name`, `imported_names`, `file_id`, `line_number` | `alias` | Transient — no `imports` table. Mapped to graph import node + imports edge. Metadata includes `module_name`, `imported_names`, `alias`, `line_number`. |
| `ParsedRoute` | Extracted route definition | Parser | Chunker, Graph Builder | `route_id`, `http_method`, `path`, `handler_function`, `file_id`, `line_number` | `decorators` | FastAPI-specific in current build |
| `CodeChunk` | Semantic code chunk | Chunker | Embedder, Storage | `chunk_id`, `file_id`, `chunk_type`, `content`, `start_line`, `end_line`, `language`, `file_path` | `symbol_id`, `symbol_name`, `content_hash`, `metadata` | Types: file_summary, function, class, method, route, test, config, readme_section |
| `EmbeddingInput` | Chunk ready for embedding | Chunker | Embedder | `chunk_id`, `content` | `metadata` | Only non-secret, non-binary chunks |
| `EmbeddingRecord` | Vector with metadata | Embedder | Storage | `chunk_id`, `embedding` (vector), `metadata` (file_path, symbol_name, chunk_type, language, start_line, end_line) | | Dimension must match model |
| `GraphNodeInput` | Graph node for storage | Graph Builder | Storage | `node_id`, `label`, `node_type`, `source_file`, `source_location`, `confidence` | `metadata` | Types: file, function, class, method, route, import, test |
| `GraphEdgeInput` | Graph edge for storage | Graph Builder | Storage | `source_node_id`, `target_node_id`, `relation`, `confidence`, `source_file` | `metadata` | Relations: defines, imports, inherits, calls, tests, handles_route |
| `StoredChunkRef` | Reference to stored chunk | Storage | Retrieval | `chunk_id`, `file_path`, `symbol_name`, `chunk_type`, `start_line`, `end_line` | `content_preview` | Used in search results |
| `RetrievalCandidate` | Search result candidate | Retrieval | Ranking | `chunk_id`, `file_path`, `symbol_name`, `relevance_score`, `retrieval_method` | `confidence`, `evidence_reason` | Before final ranking |
| `EvidenceItem` | Ranked evidence for output | Ranking, Evidence | MCP, Dashboard | `file_path`, `symbol_name`, `symbol_type`, `start_line`, `end_line`, `confidence`, `relevance_score`, `retrieval_method`, `evidence_reason` | `content_preview` | Final output format |
| `ToolResult` | MCP tool response | MCP Server | Coding Agent | `tool`, `success`, `data`, `error`, `evidence_count`, `latency_ms` | | Standard wrapper for all tools |

## 17. Dependency Rules

**Current build runtime dependencies:**

| Package | Purpose | Required |
|---------|---------|----------|
| typer | CLI framework | Yes |
| rich | CLI output formatting | Yes |
| sentence-transformers | Local embeddings (CPU only) | Yes |
| chromadb | Vector store | Yes |
| sqlite3 | Metadata store | Yes (stdlib) |
| ast | Python parsing | Yes (stdlib) |
| pydantic | Data validation | Yes |
| python-dotenv | Environment variable loading | Yes |

**Current build dev dependencies:**

| Package | Purpose | Required |
|---------|---------|----------|
| pytest | Testing framework | Yes |
| pytest-cov | Test coverage | Yes |

**Deferred dependencies (not used in first slice):**

| Package | Purpose | Status |
|---------|---------|--------|
| tree-sitter | Enhanced parsing | Reserved for later parser expansion (multi-language) |
| tree-sitter-python | Python enhanced parsing | Reserved for later parser expansion |
| streamlit | Dashboard | Deferred (stub command in first slice) |
| mcp | MCP server | Deferred (stub command in first slice) |

Tree-sitter packages must not be imported in current-build code. They are declared for later use only. If the project does not need them during the first slice, they should be moved to an optional dependency group.

**Do NOT add:**
- FastAPI (not needed for current build)
- PostgreSQL (SQLite is sufficient)
- LangChain/LangGraph (not needed for current build)
- NetworkX (optional later, not current build)
- Redis (not needed)
- Celery (not needed)
- Docker (optional for deployment, not required for local use)

## 18. What Must Stay Decoupled

| Component A | Component B | Reason |
|-------------|-------------|--------|
| Storage | MCP Server | MCP server calls storage, never modifies it directly |
| Dashboard | MCP Server | Sibling interfaces over shared services; no cross-dependency |
| Parser | Embeddings | Parser produces chunks, embeddings encodes them |
| Scanner | Parser | Scanner finds files, parser processes them |
| Graph | Retrieval | Graph provides relationships, retrieval combines with search |

## 19. Current Build Architecture Decisions

1. **No FastAPI** — Streamlit calls Python modules directly. MCP server is stdio, not HTTP.
2. **SQLite over PostgreSQL** — No Docker required. Sufficient for single-user local use.
3. **Chroma over pgvector** — Local persistent store. No database server needed.
4. **Sentence Transformers over API embeddings** — No API key needed. Runs locally.
5. **Python AST over tree-sitter only** — Python first. tree-sitter-python adds depth.
6. **Native graph over NetworkX** — Lightweight. SQL recursive queries for traversal.
7. **Typer over argparse** — Cleaner CLI UX. Standard Python CLI approach. Entry point: `fcode.cli.main:app`.

## 20. Architecture Anti-Patterns

Do NOT:

1. **Add FastAPI as a dependency** — There is no HTTP API in the current build.
2. **Create a shared state singleton** — Each service creates its own storage connection.
3. **Put business logic in CLI handlers** — CLI is thin; services do the work.
4. **Mix dashboard and MCP code** — They are separate interfaces to the same services.
5. **Import between sibling modules** — Modules depend on each other through services, not direct imports.
6. **Add LangChain/LangGraph** — Not needed for current build scope.
7. **Create abstract base classes** — One implementation per module; abstractions add when needed.

## 21. Config File Schema

`.fcode/config.json` defines the index configuration for a repository. This file must not contain API keys.

```json
{
  "schema_version": 1,
  "repo_id": "uuid",
  "repo_path": "/absolute/path/to/repo",
  "index_path": "/absolute/path/to/repo/.fcode",
  "embedding": {
    "provider": "sentence_transformers",
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "dimension": 384
  },
  "storage": {
    "sqlite_path": ".fcode/index.db",
    "chroma_path": ".fcode/chroma"
  },
  "indexing": {
    "python_only": true,
    "max_file_size_bytes": 1048576,
    "full_rebuild": true
  },
  "privacy": {
    "local_only": true,
    "allow_cloud_llm": false
  }
}
```

**Rules:**
- This file is repo-local inside `.fcode/`.
- If embedding model or dimension changes, F Code must require full reindex.
- `allow_cloud_llm` defaults to `false`.
- Schema version tracks config format for future migrations.

## 22. Locked Architecture Decisions

1. **MCP server process model:** Subprocess via `fcode mcp --repo <path>` that the coding agent launches.
2. **Dashboard SQLite connection:** Separate connections; SQLite handles concurrent reads fine.
3. **Monorepo subdirectory indexing:** Not in current build; one repo per index.
4. **Graph traversal method:** SQL recursive CTE for 2-hop queries; direct SQL for 1-hop lookups. In-memory traversal allowed only in tests and debugging utilities.
5. **Embedding model:** Configurable via `.fcode/config.json` with default `sentence-transformers/all-MiniLM-L6-v2`, dimension 384. Changing model or dimension requires full reindex.
