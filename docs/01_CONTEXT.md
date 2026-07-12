# 01_CONTEXT.md — F Code Master Context

## 1. Project Name

**F Code**

## 2. One-Sentence Definition

F Code is a local repository intelligence tool that helps AI coding agents avoid writing code that already exists.

## 3. Core Product Thesis

F Code gives coding agents local, evidence-backed repository intelligence before implementation. It indexes a repository, extracts code relationships, stores them locally, and exposes search and planning tools through MCP so agents can check for existing implementations, find related code, and plan minimal changes — all without leaving their workflow.

## 3a. Eligibility Definition

A path counts as an eligible file when the scanner will create a row for it in the `files` table. An eligible file must:

- be inside the repository root
- not be ignored by hardcoded rules
- not be ignored by `.gitignore`
- not be ignored by `.fcodeignore`
- not be inside `.fcode/`
- not be a symlink
- not be inside a symlinked directory
- be readable
- not be binary
- not be an `.env` family file
- be no larger than 1,048,576 bytes

Eligible files include Python files, Markdown and RST files, recognized configuration files, and other readable text files that the scanner records.

Secret-bearing source files remain eligible: create a `files` row, set `has_secrets = true`, include their size in repository-limit calculations, do not create embeddings from unredacted secret content.

## 3b. Single Discovery Scan

The filesystem is walked once per indexing attempt:

1. Phase A performs one read-only discovery scan.
2. The scanner applies ignores, symlink rules, size checks, readability checks, binary detection, and secret detection.
3. It returns an ordered `ScannedFile` collection, eligible-file count, eligible total bytes, and skipped-file diagnostics.
4. Phase A uses these results for repository-limit checks.
5. Phase B reuses the same `ScannedFile` collection.
6. Phase B must not perform another filesystem walk.
7. Repository-change detection between Phase A and Phase B is not implemented in the first slice.
8. The Phase A discovery result is the source of truth for one index run.

## 4. Primary Problem

When a coding agent works on an unfamiliar repository, it does not know what already exists. It may:
- Reimplement a function that already exists in another file
- Create a new file when an existing file should be extended
- Suggest changes that break related code
- Ignore existing tests that cover the area being changed

F Code solves this by giving agents a local intelligence layer that answers "does this already exist?" before they write code.

## 5. Target Users

**Primary:** Developers using AI coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI, etc.) who want those agents to be repository-aware.

**Secondary:** Human developers who want to inspect a repository's structure, relationships, and reuse opportunities through a local dashboard.

## 6. Main Use Cases

1. **Duplicate prevention** — Agent checks if requested functionality already exists before writing new code.
2. **Reuse discovery** — Agent finds existing functions, classes, or modules that can be extended instead of creating new ones.
3. **Impact analysis** — Agent understands what will break if a specific function or file is changed.
4. **Minimal change planning** — Agent recommends the smallest set of changes to existing files.
5. **Repository inspection** — Human developer browses repository wiki, structure, and relationships through a local dashboard.

## 7. Current Build Scope

MCP, dashboard, and retrieval user workflows are deferred in the current build.

- Python CLI package (`fcode`)
- SQLite for metadata, graph, and keyword search
- Chroma local persistent vector store
- Sentence Transformers local embeddings
- Python parsing first (no multi-language)
- Lightweight native code graph layer
- GitHub public repos and ZIP upload only
- No automatic patch application
- No private repo auth/login

## 8. Explicitly Out of Scope

- Multi-language parsing (TypeScript, Go, Rust, etc.) — later only
- Private repository authentication — later only
- Automatic code patching/application — later only
- Cloud deployment or hosted SaaS — later only
- Team/collaboration features — later only
- CI/CD integration — later only
- Architecture diagram generation — later only
- PR review automation — later only
- React frontend — not needed; Streamlit is the UI
- PostgreSQL — SQLite is sufficient for current build
- FastAPI — not needed for current build; Streamlit calls local Python directly. FastAPI route detection is only for indexed target repositories that use FastAPI, not for F Code's own runtime
- Graphify as direct dependency — inspiration only
- Ponytail as direct dependency — principles embedded in prompts only

## 9. Local-First Principle

F Code runs entirely on the user's laptop. No code is uploaded to any external server. All indexing, storage, retrieval, and tool serving happens locally. The only network calls are:
- Cloning a public GitHub repository (user-initiated)
- Embedding generation (local Sentence Transformers, no API)

## 10. Privacy Principle

Repository source code never leaves the user's machine. F Code does not send code to external APIs for indexing or retrieval. All embeddings are generated locally. All search is local. All MCP tools are local stdio.

## 11. Agent-First Principle

F Code's primary interface is MCP tools for coding agents. The human dashboard is secondary. Every feature must first answer: "Does this help a coding agent work better on a repository?"

## 12. Human Dashboard Principle

The Streamlit dashboard is for human inspection, not the primary workflow. It helps users:
- See what F Code indexed
- Test queries manually
- Preview what MCP tools return
- Inspect repository wiki/structure

## 13. Anti-Duplication Principle

The core value of F Code is preventing duplicate code. Every retrieval result, every plan, every suggestion should first check: "Does something similar already exist?"

## 14. Minimal Change Principle

When recommending changes, F Code should recommend modifying existing files over creating new ones, extending existing classes over creating new abstractions, and the smallest diff that solves the problem.

## 15. Core Interfaces

| Interface | Purpose | Technology |
|-----------|---------|------------|
| CLI | Primary entry point | Python Typer |
| MCP stdio tools | Coding agent interface | MCP protocol |
| Streamlit dashboard | Human inspection | Streamlit |
| Local storage | All index data | SQLite + Chroma |

## 16. Core Technical Stack

| Component | Technology | Reason |
|-----------|------------|--------|
| Language | Python 3.10+ | Locked decision |
| CLI framework | Typer | Locked decision — current build |
| Vector store | Chroma PersistentClient | Local, simple, no Docker |
| Embeddings | Sentence Transformers | Local, no API |
| Metadata store | SQLite | No Docker, sufficient for single-user |
| Keyword search | SQLite FTS5 | Built into SQLite |
| Code graph | Native Python (dicts/lists + NetworkX optional) | Lightweight |
| Code parsing | Python `ast` (tree-sitter-python reserved for later expansion) | Python first |
| Dashboard | Streamlit | Local, simple |
| MCP server | mcp Python SDK | Stdio transport |

## 17. Storage Direction

All storage is local:
- SQLite database in `.fcode/` directory inside the repository
- Chroma persistent store in `.fcode/chroma/` directory
- Generated reports in `.fcode/reports/` directory
- No cloud database, no remote storage

## 18. Deferred Retrieval Direction

Hybrid retrieval combining:
1. Semantic vector search (Chroma + Sentence Transformers)
2. Keyword/symbol search (SQLite FTS5)
3. Exact symbol lookup (SQLite)
4. Metadata filtering (SQLite)
5. Graph relationship expansion (SQLite recursive CTE for 2-hop; direct SQL for 1-hop)

## 19. Code Graph Direction

Lightweight native graph layer:
- Nodes: file, function, class, method, route, import, test (variables do not become graph nodes)
- Edges: defines, imports, inherits, calls, tests, handles_route
- Confidence labels: EXTRACTED, INFERRED, AMBIGUOUS
- Stored in SQLite tables (`code_nodes`, `code_edges`)
- Traversed with SQL recursive CTE for 2-hop queries; direct SQL for 1-hop lookups
- In-memory traversal allowed only in tests and debugging utilities
- No NetworkX dependency in current build (optional later)

## 20. Deferred MCP Direction

MCP tools are read-only and planning-only:
- `search_code` — semantic + keyword search
- `find_symbol` — exact symbol lookup
- `get_file_context` — file summary and structure
- `find_related_files` — graph-based related file discovery
- `check_existing_implementation` — duplicate prevention check
- `plan_minimal_change` — minimal change plan generation
- `find_related_tests` — test discovery
- `explain_change_impact` — impact analysis

## 21. Deferred Dashboard Direction

Five pages:
1. Connect Repository — upload ZIP or enter GitHub URL
2. Indexing Status — progress and results
3. Repository Wiki — structure, symbols, summary
4. Ask Repository — natural language Q&A
5. Agent Tools Preview — test MCP tools manually

## 22. Graphify Position

Graphify is a development helper and inspiration source only. It is NOT a runtime dependency.

**Use for inspiration:**
- Node/edge schema design (`{id, label, source_file, source_location}` + `{source, target, relation, confidence}`)
- EXTRACTED/INFERRED/AMBIGUOUS confidence labels
- tree-sitter AST extraction pattern
- File detection and filtering approach

**Do not:**
- Import Graphify modules
- Add Graphify to dependencies
- Call Graphify at runtime

## 23. Ponytail Position

Ponytail is a development discipline and inspiration source only. It is NOT a runtime dependency.

**Use for inspiration:**
- 7-rung minimal solution ladder (embed in agent prompts)
- "No abstractions not requested" rule
- "Deletion over addition" principle
- Root-cause debugging approach

**Do not:**
- Install Ponytail as a package
- Import Ponytail modules
- Call Ponytail at runtime

## 24. Security Rules

1. No code leaves the user's machine.
2. No API keys stored in plain text.
3. `.env` files and secrets detected and redacted.
4. MCP server is local stdio only — no network.
5. Dashboard is localhost only — no external access.
6. Generated reports contain no secrets.
7. No automatic file writes from MCP tools.
8. No shell command execution from MCP tools.

## 25. Naming Rules

- Product name: **F Code** (always two words, capital F, capital C)
- CLI command: `fcode`
- Package name: `fcode`
- Index directory: `.fcode/`
- Python package: `fcode/`
- Config file: `.fcode/config.json`
- Database file: `.fcode/index.db`
- Chroma directory: `.fcode/chroma/`

## 26. Documentation Rules

All documentation lives in `docs/`. The documentation set:

| File | Purpose |
|------|---------|
| `AGENTS.md` | Root rule file for all agents |
| `docs/01_CONTEXT.md` | Master context and locked decisions |
| `docs/02_PRODUCT_SPEC.md` | Product specification |
| `docs/03_SYSTEM_ARCHITECTURE.md` | System architecture |
| `docs/04_DATA_MODEL.md` | Storage and data model |
| `docs/05_INDEXING_AND_RETRIEVAL.md` | Indexing and retrieval pipeline |
| `docs/06_MCP_TOOLS_CONTRACT.md` | MCP tool schemas and contracts |
| `docs/07_DASHBOARD_SPEC.md` | Streamlit dashboard specification |
| `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md` | Test scenarios and acceptance criteria |
| `docs/09_AGENT_TASKS.md` | Parallel agent work packages |

No other documentation files should be created without updating this list.

Archived documents in `docs/archive/` are historical context only and must not override current docs. Coding agents must not follow archived reports as current requirements.

## 27. Implementation Specification Freeze

### 27.1 Authoritative Sources

The authoritative implementation sources for the current build are:

- `AGENTS.md`
- `docs/01_CONTEXT.md` through `docs/09_AGENT_TASKS.md`

These documents define the current-build implementation contract. No other file is authoritative for implementation decisions.

### 27.2 Freeze Rules

1. Coding agents must not reopen or replace locked decisions documented in the authoritative sources.
2. An implementation discovery that conflicts with documented behavior may not be silently resolved.
3. A proposed contract change must be reported using the CHANGE-REQUEST format defined in `AGENTS.md` Section 18.2.
4. No agent may change persisted schema, public CLI, MCP tool schema, error vocabulary, ownership, first-slice scope, or storage behavior without an accepted documentation change.
5. Implementation convenience is not permission to change the specification.
6. Minor internal implementation details that do not affect observable behavior, shared contracts, persisted data, ownership, or tests may be selected locally.
7. After this freeze, future review must be scoped to the implementation slice being built. Do not restart a full-project documentation audit unless a product-level change is requested.

## 28. Repository Limits (Mandatory)

These limits are mandatory hard limits for the current build:

| Limit | Value | Behavior |
|-------|-------|----------|
| Maximum eligible files | 10,000 | Abort preflight, exit code 1, `repository_limit_exceeded` |
| Maximum total eligible content | 52,428,800 bytes (50 MiB) | Abort preflight, exit code 1, `repository_limit_exceeded` |
| Maximum individual file size | 1,048,576 bytes | Skip file, log `file_skipped`, continue |

## 29a. Work Package 0 — Shared Contracts

WP0 (`fcode/contracts/`) is the canonical definition of all shared enums, models,
errors, and protocol interfaces used across the codebase.

- Owned by the Integration/Contracts Agent
- Read before any feature work
- No feature module may duplicate WP0 definitions
- Changed only through the CHANGE-REQUEST process in Section 27

## 30. Locked Decisions

1. **CLI framework:** Locked: Typer. Entry point: `fcode.cli.main:app`.
2. **Embedding model:** Locked: `sentence-transformers/all-MiniLM-L6-v2` (dimension 384). `all-mpnet-base-v2` is not current build. Changing embedding model or dimension requires full reindex.
3. **Graph traversal depth:** Locked: 2 hops max for current build. Uses SQL recursive CTE.
4. **Repository size limits:** Hard limits as defined in Section 28.
5. **Reindexing strategy:** Locked: full rebuild for current build. Incremental reindexing is out of scope.
6. **Report format:** Markdown for human, JSON for machine.
7. **Config file format:** Locked: JSON for simplicity.
8. **Testing framework:** Locked: pytest. All unit and integration tests use pytest.
