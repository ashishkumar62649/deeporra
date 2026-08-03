# AGENTS.md — DeepOrra Root Rule File

## 1. Project Identity

**DeepOrra** is a local-first repository intelligence tool that helps AI coding agents avoid writing code that already exists.

This file is the root instruction file for all coding agents working on DeepOrra. Read it before any work.

## 2. Non-Negotiable Rules

1. Never guess missing product decisions. Report them as open questions.
2. Never edit files outside your assigned ownership without explicit approval.
3. Never add dependencies without checking if stdlib or existing deps cover the need.
4. Never create abstractions with one implementation.
5. Never create documentation files not listed in the task routing table.
6. Always update relevant docs when implementation changes contracts.
7. Always report what you changed, what you didn't touch, and what's uncertain.
8. Always follow minimal change discipline (see Section 10).

## 3. Current Build Scope

- CLI-first Python package
- Local Streamlit dashboard (localhost only)
- Local MCP stdio server (read-only/planning-only)
- SQLite for metadata, graph, and keyword search
- Chroma local persistent vector store
- Sentence Transformers local embeddings
- Python parsing first (no multi-language)
- Lightweight native code graph layer
- GitHub public repos and ZIP upload only
- No automatic patch application
- No private repo auth/login
- No hosted SaaS
- No React frontend
- No Graphify direct dependency
- No Ponytail direct dependency

## 4. Out of Scope

- Multi-language parsing (TypeScript, Go, etc.) — later only
- Private repository authentication — later only
- Automatic code patching — later only
- Cloud deployment — later only
- Team/collaboration features — later only
- CI/CD integration — later only
- Architecture diagram generation — later only
- PR review automation — later only

## 5. Mandatory First Step Before Any Work

Before editing any file, the agent must respond with:

1. **Detected task type** (from the routing table below)
2. **Documents it will read** before starting
3. **Files it expects to edit**
4. **Files it will not touch**
5. **Uncertainties or blockers**

Do not start work until this declaration is complete.

## 6. Task Routing Table

| Task Type | Required Docs | Allowed Folders |
|-----------|--------------|-----------------|
| Shared contracts (WP0) | `01_CONTEXT.md` | `deeporra/contracts/` |
| CLI commands, config | `01_CONTEXT.md`, `03_SYSTEM_ARCHITECTURE.md` | `deeporra/cli/`, `deeporra/config/` |
| Database, storage, schema | `01_CONTEXT.md`, `04_DATA_MODEL.md` | `deeporra/storage/` |
| File scanning, parsing, graph extraction | `01_CONTEXT.md`, `05_INDEXING_AND_RETRIEVAL.md` | `deeporra/scanner/`, `deeporra/parser/`, `deeporra/graph/graph_builder.py` |
| Chunking, embeddings | `01_CONTEXT.md`, `05_INDEXING_AND_RETRIEVAL.md` | `deeporra/chunking/`, `deeporra/embeddings/` |
| Retrieval, graph | `01_CONTEXT.md`, `04_DATA_MODEL.md`, `05_INDEXING_AND_RETRIEVAL.md` | `deeporra/retrieval/`, `deeporra/graph/` |
| MCP tools | `01_CONTEXT.md`, `06_MCP_TOOLS_CONTRACT.md` | `deeporra/mcp_server/` |
| Dashboard, UI | `01_CONTEXT.md`, `07_DASHBOARD_SPEC.md` | `deeporra/dashboard/` |
| Reports, wiki | `01_CONTEXT.md`, `07_DASHBOARD_SPEC.md` | `deeporra/reports/` |
| Tests, scenarios | `01_CONTEXT.md`, `08_SCENARIOS_AND_ACCEPTANCE_TESTS.md` | `tests/` |
| Parallel task assignment | `01_CONTEXT.md`, `09_AGENT_TASKS.md` | Per work package |
| Architecture decisions | `01_CONTEXT.md`, `03_SYSTEM_ARCHITECTURE.md` | Any (report only) |

## 7. File Ownership Rules

| Owner | Allowed Folders | Forbidden Folders |
|-------|----------------|-------------------|
| Contracts Agent | `deeporra/contracts/` | All feature module folders |
| CLI/Config Agent | `deeporra/cli/`, `deeporra/config/`, `deeporra/utils/` | `deeporra/mcp_server/`, `deeporra/dashboard/`, `tests/` |
| Storage Agent | `deeporra/storage/` | `deeporra/cli/`, `deeporra/mcp_server/`, `deeporra/dashboard/` |
| Scanner/Parser Agent | `deeporra/scanner/`, `deeporra/parser/`, `deeporra/graph/graph_builder.py` | `deeporra/storage/`, `deeporra/mcp_server/`, `deeporra/dashboard/`, `deeporra/graph/graph_traverser.py`, `deeporra/graph/impact_analyzer.py` |
| Chunking/Embeddings Agent | `deeporra/chunking/`, `deeporra/embeddings/` | `deeporra/parser/`, `deeporra/mcp_server/`, `deeporra/dashboard/` |
| Retrieval/Graph Agent | `deeporra/retrieval/`, `deeporra/graph/` | `deeporra/cli/`, `deeporra/mcp_server/`, `deeporra/dashboard/` |
| MCP Server Agent | `deeporra/mcp_server/` | `deeporra/cli/`, `deeporra/dashboard/`, `deeporra/storage/` |
| Dashboard Agent | `deeporra/dashboard/` | `deeporra/mcp_server/`, `deeporra/storage/`, `deeporra/cli/` |
| Reports/Wiki Agent | `deeporra/reports/` | `deeporra/mcp_server/`, `deeporra/cli/`, `deeporra/dashboard/` |
| Tests Agent | `tests/` | `deeporra/` (no production code) |

## 8. Parallel Work Rules

1. No agent may change shared contracts (tool schema, database schema, folder structure, command names, scope) without stopping and reporting the change.
2. Each agent reads only the docs listed in the routing table for its task type.
3. Each agent edits only the folders listed in its ownership row.
4. Shared files (`deeporra/config/`, `deeporra/storage/`, `deeporra/utils/`) require explicit coordination.
5. When two agents need the same file, the agent that needs it more gets it; the other waits.
6. Conflicts are resolved by the project owner, not by agents guessing.

## 9. Documentation Update Rules

Update the relevant doc when implementation changes it: tool schema → `06_MCP_TOOLS_CONTRACT.md`; database tables → `04_DATA_MODEL.md`; CLI commands → `03_SYSTEM_ARCHITECTURE.md`; dashboard pages → `07_DASHBOARD_SPEC.md`; new scenarios → `08_SCENARIOS_AND_ACCEPTANCE_TESTS.md`; work-package boundaries → `09_AGENT_TASKS.md`.

## 10. Minimal Change Discipline

1. Reuse before building: the feature itself, an extendable module, stdlib, or an installed dependency — in that order.
2. Smallest change that works: modify before creating, extend before abstracting, no boilerplate, wrappers, or "future-proofing," no new dependencies unless necessary.
3. Mark uncertain suggestions with a confidence level.
4. Non-trivial logic leaves one runnable check (assert or small test).

## 11. Graphify Usage Rules

Graphify is a development helper only. It is NOT a runtime dependency.

- Use Graphify to inspect a repository's graph structure during development.
- Use Graphify's node/edge schema as inspiration for DeepOrra's `code_nodes`/`code_edges` tables.
- Use Graphify's EXTRACTED/INFERRED/AMBIGUOUS confidence labels as inspiration.
- Do NOT import Graphify modules into DeepOrra source.
- Do NOT add Graphify to `requirements.txt` or `pyproject.toml`.
- Do NOT call Graphify at runtime.

## 12. Ponytail Usage Rules

Ponytail is a development discipline only. It is NOT a runtime dependency.

- Follow Ponytail's 7-rung minimal solution ladder when implementing.
- Embed Ponytail-style rules into DeepOrra's agent prompts (planner, test generator).
- Do NOT install Ponytail as a package dependency.
- Do NOT import Ponytail modules into DeepOrra source.
- Do NOT call Ponytail at runtime.

## 13. Security and Privacy Rules

1. DeepOrra runs on the user's laptop. No code leaves the machine.
2. No repository code is uploaded to any server.
3. No API keys are stored in plain text.
4. `.env` files and secrets are detected and redacted from indexing.
5. The MCP server is local stdio only. No network exposure.
6. The dashboard is localhost only. No external access.
7. Generated reports contain no secrets or API keys.

## 14. MCP Tool Safety Rules

Current build MCP tools must not:

- Write, edit, or delete any files
- Run shell commands
- Install dependencies
- Apply patches or generate diffs
- Upload code to any server
- Access the network

MCP tools are read-only and planning-only.

## 15. Completion Report Format

After completing any task, the agent must report:

```
## Completion Report

**Files changed:**
- list of files modified/created

**What was implemented:**
- brief description

**What docs were updated:**
- list of docs updated, or "none"

**What tests/checks were run:**
- list of tests executed

**Blockers:**
- any issues encountered, or "none"

**Contract changes:**
- any shared contracts that changed, or "none"

**Matches docs:**
- yes / no (explain if no)
```

## 16. What To Do When Unsure

1. Stop working.
2. Report what you're unsure about.
3. List the options you see.
4. Wait for direction.
5. Do not guess. Do not proceed. Do not add what you're unsure about.

---

*This file is the root rule file. Every coding agent working on DeepOrra must read it first.*

## 17. Archived Documents

Files in `docs/archive/` are historical context only and must not override current docs. Coding agents must not follow archived reports as current requirements. Only `AGENTS.md` and `docs/01_CONTEXT.md` through `docs/09_AGENT_TASKS.md` are authoritative for implementation.

## 18. Implementation Specification Freeze

### 18.1 Authoritative Sources

The authoritative implementation sources for the current build are:

- `AGENTS.md`
- `docs/01_CONTEXT.md` through `docs/09_AGENT_TASKS.md`

These documents define the current-build implementation contract. No other file is authoritative for implementation decisions.

### 18.2 Freeze Rules

1. Coding agents must not reopen or replace locked decisions documented in the authoritative sources.
2. An implementation discovery that conflicts with documented behavior may not be silently resolved.
3. A proposed contract change must be reported using this format:

```
CHANGE-REQUEST ID
Affected contract
Current documented rule
Observed implementation problem
Proposed exact replacement
Schema/API/test impact
Blocking status
```

4. No agent may change the following without an accepted documentation change:
   - Persisted schema (SQLite tables, columns, constraints)
   - Public CLI (command names, arguments, exit codes)
   - MCP tool schema (tool names, input/output fields)
   - Error vocabulary (error codes, warning codes)
   - Ownership (which agent owns which files)
   - First-slice scope (what is included vs deferred)
   - Storage behavior (how SQLite, Chroma, FTS5 are written)

5. Implementation convenience is not permission to change the specification.
6. Minor internal implementation details that do not affect observable behavior, shared contracts, persisted data, ownership, or tests may be selected locally.
7. After this freeze, future review must be scoped to the implementation slice being built. Do not restart a full-project documentation audit unless a product-level change is requested.

## 19. Repository Limits (Mandatory)

These limits are mandatory hard limits for the current build:

| Limit | Value | Behavior |
|-------|-------|----------|
| Maximum eligible files | 10,000 | Abort preflight, exit code 1, `repository_limit_exceeded` |
| Maximum total eligible content | 52,428,800 bytes (50 MiB) | Abort preflight, exit code 1, `repository_limit_exceeded` |
| Maximum individual file size | 1,048,576 bytes | Skip file, log `file_skipped`, continue |

## 20. Pipeline Module Boundaries

`deeporra/indexing/index_service.py` is owned by the Integration Agent.

It is the only module that controls:
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

Storage module boundaries:
- `sqlite_store.py` accesses SQLite only.
- `chroma_store.py` accesses Chroma only.
- `graph_store.py` accesses graph tables in SQLite only.
- `fts_store.py` accesses FTS5/SQLite only.
- Storage modules do not call each other.
- Storage modules do not control the full pipeline.
- Parser, scanner, graph builder, chunker, and embedder do not call persistence modules directly.
- `index_service.py` calls each module through its public interface.

## 21. Test Ownership

### Feature Agents

Each feature agent owns and writes the unit tests for its modules:

- **CLI/Config Agent:** `tests/unit/test_index_cmd.py`, `test_status_cmd.py`, `test_doctor_cmd.py`, `test_deferred_commands.py`, config and utility tests
- **Scanner/Parser Agent:** `tests/unit/test_file_scanner.py`, `test_ignore_rules.py`, `test_secret_detector.py`, `test_python_ast.py`, `test_symbol_extractor.py`, `test_import_extractor.py`, `test_route_detector.py`, `test_graph_builder.py`
- **Storage Agent:** SQLite, Chroma, graph-store, and FTS tests
- **Chunking/Embeddings Agent:** chunker and encoder tests

### Tests Agent

The Tests Agent owns:
- `tests/golden/`
- Cross-module integration tests
- Failure-cleanup tests
- Scenario-matrix tests
- Acceptance tests

The Tests Agent may run feature-owned unit tests but must not rewrite them without routing the change through the owning agent.

## 22. First-Slice Work Packages

Implementation order:

```
WP0 → WP1 + WP2 + WP3 → WP4 → WP5 → WP6
```

### WP1 — CLI and Config

**Functional commands:** `index`, `status`, `doctor`

**Deferred stubs (exit code 2):** `dashboard`, `mcp`, `setup`

**Owned files:** `deeporra/cli/`, `deeporra/config/`, `deeporra/utils/`

### WP2 — Storage

**Owned files:** `deeporra/storage/`

Includes SQLite schema and migrations, Chroma persistence, FTS5, graph persistence.

### WP3 — Scanner, Parser, and Graph Extraction

**Owned files:** `deeporra/scanner/`, `deeporra/parser/`, `deeporra/graph/graph_builder.py`

Includes scanner, ignore rules, secret detection, Python AST, symbols, imports, routes, graph builder.

### WP4 — Chunking and Embeddings

**Owned files:** `deeporra/chunking/`, `deeporra/embeddings/`

Includes chunk creation, local CPU embeddings, warning handling.

### WP5 — Integration

**Owned files:** `deeporra/indexing/`

Includes `deeporra/indexing/index_service.py`, full pipeline wiring, state transitions, failure cleanup, verification counts.

### WP6 — First-Slice Tests

**Owned files:** `tests/`

Includes golden repositories, cross-module scenarios, cleanup/failure tests, acceptance matrix.

Some agents may work in parallel only when they edit disjoint owned files.
