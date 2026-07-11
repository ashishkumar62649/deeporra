# 09_AGENT_TASKS.md — F Code First-Slice Work Packages

## 1. Purpose

This document defines the first-slice work packages for the F Code project. It divides implementation into discrete, sequentially executable packages that prevent agents from overwriting each other, editing unrelated files, or inventing contracts.

## 2. Implementation Order

```
WP0 → WP1 + WP2 + WP3 → WP4 → WP5 → WP6
```

Some agents may work in parallel only when they edit disjoint owned files.

## 3. Parallel Work Rules

1. No agent may change shared contracts without stopping and reporting with a CHANGE-REQUEST (see `AGENTS.md` Section 18.2).
2. Each agent reads only the docs listed in its work package.
3. Each agent edits only the folders listed in its ownership.
4. Shared files (`fcode/config/`, `fcode/storage/`, `fcode/utils/`) require explicit coordination.
5. When two agents need the same file, the agent that needs it more gets it; the other waits.
6. Conflicts are resolved by the project owner, not by agents guessing.

### Shared Utility Folder: `fcode/utils/`

`fcode/utils/` is owned by the CLI/Config Agent. Other agents may add utility functions only if:
- The utility is used by at least two packages.
- The task report explicitly justifies it.
- No domain-specific package is a better home.

Domain-specific helpers must stay in their domain folders, not `fcode/utils/`.

## 4. Required Docs Before Work

Before any work, agents must read:
- `AGENTS.md` — root rules (especially Sections 18-22)
- `docs/01_CONTEXT.md` — project context, eligibility, freeze rules
- Their specific work package docs (see routing table below)

## 5. Work Package Format

Each work package defines:
- Agent name
- Goal
- Required docs
- Allowed files/folders
- Forbidden files/folders
- Dependencies
- Expected outputs
- Required tests (per test-ownership rules in `AGENTS.md` Section 21)
- Documentation updates
- Completion report

---

## 6. Work Package 0: Shared Contracts

**Agent Name:** Integration/Contracts Agent

**Goal:** Define all shared enums, data models, error codes, and protocol interfaces
that every feature module depends on. Eliminate duplicate definitions across modules.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`

**Allowed Files/Folders:**
- `fcode/contracts/`

**Forbidden Files/Folders:**
- Any feature module folder (cli, storage, scanner, parser, chunking, embeddings, indexing, graph, retrieval, mcp_server, dashboard, reports)

**Dependencies:** None (this is the first work package)

**Expected Outputs:**
- `fcode/contracts/__init__.py` — package init with `__all__`
- `fcode/contracts/enums.py` — `IndexPhase`, `IndexState`, `ParseStatus`, `FileType`, `SymbolType`, `GraphNodeType`, `GraphRelation`, `HttpMethod`, `Confidence`, `ChunkType`, `SearchMode`, `DiagnosticSeverity`, `SupportedSetupAgent`
- `fcode/contracts/models.py` — all dataclasses (`RepoInput`, `ScannedFile`, `SkipFileDiagnostic`, `ScanResult`, `ParsedSymbol`, `ParsedImport`, `ParsedRoute`, `ParsedFile`, `GraphBuildResult`, `CodeChunk`, `EmbeddingRecord`, `EmbeddingBatchResult`, `StoredChunkRef`, `IndexCounts`, `IndexRunResult`, `IndexDiagnostic`, `IndexStatusRecord`, `DoctorCheck`, `DoctorResult`, `EvidenceItem`, `RetrievalCandidate`, `FCodeConfig`, `ToolResult`, `ToolError`, `EmbeddingInput`, `EmbeddingMetadata`, `GraphNodeInput`, `GraphEdgeInput`)
- `fcode/contracts/errors.py` — `ErrorCode`, `McpErrorCode`
- `fcode/contracts/interfaces.py` — protocol interfaces for all feature modules

**Required Tests (owned by Integration/Contracts Agent):**
- `tests/unit/test_contracts.py` — enum values, model defaults
- `tests/unit/test_contract_errors.py` — error code conventions
- `tests/unit/test_contract_interfaces.py` — protocol method signatures

**Documentation Updates:**
- Update `docs/01_CONTEXT.md` to reference WP0
- Update `docs/03_SYSTEM_ARCHITECTURE.md` to include `fcode/contracts/`

**Completion Report:**
```
## Completion Report — Contracts Agent

**Files changed:**
- fcode/contracts/*.py

**What was implemented:**
- Shared enums, models, errors, protocol interfaces

**What docs were updated:**
- docs/01_CONTEXT.md

**What tests/checks were run:**
- tests/unit/test_contracts.py
- tests/unit/test_contract_errors.py
- tests/unit/test_contract_interfaces.py

**Blockers:**
- none

**Contract changes:**
- This IS the contract; all feature agents start from here
```

---

## 7. Work Package 1: CLI and Config

**Agent Name:** CLI/Config Agent

**Goal:** Implement the CLI entry point, configuration management, and all functional and deferred-stub CLI commands.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md` (including WP0 reference)
- `docs/03_SYSTEM_ARCHITECTURE.md`

**Allowed Files/Folders:**
- `fcode/cli/`
- `fcode/config/`
- `fcode/utils/`
- `fcode/__init__.py`
- `fcode/__main__.py`
- `fcode/contracts/` (read-only imports)

**Forbidden Files/Folders:**
- `fcode/mcp_server/`
- `fcode/dashboard/`
- `fcode/storage/`
- `fcode/parser/`
- `fcode/scanner/`
- `fcode/chunking/`
- `fcode/embeddings/`
- `fcode/indexing/`
- `fcode/graph/`
- `fcode/retrieval/`

**Dependencies:** None (this agent can start first)

**Functional commands:**
- `fcode index <repo_path>` — accept path, validate, call `index_service`, print result
- `fcode status [repo_path]` — query SQLite for index status, print
- `fcode doctor` — check dependencies (Python version, imports, model availability)

**Deferred stubs (exit code 2):**
- `fcode dashboard` — print "This command is not available in the first implementation slice.", exit 2
- `fcode mcp --repo <repo_path>` — same
- `fcode setup <agent> --repo <repo_path>` — same

**Expected Outputs:**
- `fcode/cli/main.py` — Typer app (entry point: `fcode.cli.main:app`)
- `fcode/cli/index_cmd.py` — `fcode index` command
- `fcode/cli/status_cmd.py` — `fcode status` command
- `fcode/cli/dashboard_cmd.py` — `fcode dashboard` stub
- `fcode/cli/mcp_cmd.py` — `fcode mcp` stub
- `fcode/cli/doctor_cmd.py` — `fcode doctor` command
- `fcode/cli/setup_cmd.py` — `fcode setup` stub
- `fcode/config/settings.py` — configuration management
- `fcode/config/defaults.py` — default values
- `fcode/__main__.py` — entry point

**Required Tests (owned by CLI/Config Agent):**
- `tests/unit/test_index_cmd.py`
- `tests/unit/test_status_cmd.py`
- `tests/unit/test_doctor_cmd.py`
- `tests/unit/test_deferred_commands.py`

**Documentation Updates:**
- Update `docs/03_SYSTEM_ARCHITECTURE.md` if folder structure changes

**Completion Report:**
```
## Completion Report — CLI/Config Agent

**Files changed:**
- list

**What was implemented:**
- CLI commands, config management

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 8. Work Package 2: Storage

**Agent Name:** Storage Agent

**Goal:** Implement SQLite storage (schema, migrations, CRUD), Chroma persistence, graph store, and FTS5 keyword search.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`
- `docs/04_DATA_MODEL.md`

**Allowed Files/Folders:**
- `fcode/storage/`
- `fcode/contracts/` (read-only imports)

**Forbidden Files/Folders:**
- `fcode/cli/`
- `fcode/mcp_server/`
- `fcode/dashboard/`
- `fcode/parser/`
- `fcode/scanner/`
- `fcode/chunking/`
- `fcode/embeddings/`
- `fcode/indexing/`
- `fcode/graph/`
- `fcode/retrieval/`

**Dependencies:** None (can start in parallel with WP1 and WP3)

**Expected Outputs:**
- `fcode/storage/sqlite_store.py` — SQLite operations (repositories, files, symbols, chunks, code_nodes, code_edges, index_status, repo_reports, tool_call_logs, schema_version)
- `fcode/storage/chroma_store.py` — Chroma operations (code_chunks collection, upsert, delete by repo_id, query)
- `fcode/storage/graph_store.py` — code_nodes, code_edges table operations
- `fcode/storage/fts_store.py` — FTS5 (create, rebuild, search chunks_fts and symbols_fts, LIKE fallback)
- `fcode/storage/migrations/` — schema migration scripts

**Storage module boundaries (must not violate):**
- `sqlite_store.py` accesses SQLite only.
- `chroma_store.py` accesses Chroma only.
- `graph_store.py` accesses graph tables in SQLite only.
- `fts_store.py` accesses FTS5/SQLite only.
- Storage modules do not call each other.
- Storage modules do not control the full pipeline.

**Required Tests (owned by Storage Agent):**
- `tests/unit/test_sqlite_store.py`
- `tests/unit/test_chroma_store.py`
- `tests/unit/test_graph_store.py`
- `tests/unit/test_fts_store.py`

**Documentation Updates:**
- Update `docs/04_DATA_MODEL.md` if table schema changes

**Completion Report:**
```
## Completion Report — Storage Agent

**Files changed:**
- list

**What was implemented:**
- SQLite, Chroma, FTS5 storage

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 9. Work Package 3: Scanner, Parser, and Graph Extraction

**Agent Name:** Scanner/Parser Agent

**Goal:** Implement file scanning (eligibility, ignore rules, secret detection), Python AST parsing (symbols, imports, routes), and code graph building (nodes, edges).

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`
- `docs/05_INDEXING_AND_RETRIEVAL.md`

**Allowed Files/Folders:**
- `fcode/scanner/`
- `fcode/parser/`
- `fcode/graph/graph_builder.py`
- `fcode/contracts/` (read-only imports)

**Forbidden Files/Folders:**
- `fcode/storage/`
- `fcode/mcp_server/`
- `fcode/dashboard/`
- `fcode/graph/graph_traverser.py`
- `fcode/graph/impact_analyzer.py`
- `fcode/indexing/`
- `fcode/cli/`

**Dependencies:** None (can start in parallel with WP1 and WP2)

**Expected Outputs:**
- `fcode/scanner/file_scanner.py` — file discovery with eligibility, single scan, sorted deterministic order
- `fcode/scanner/ignore_rules.py` — `.gitignore`, `.fcodeignore`, hardcoded ignores
- `fcode/scanner/secret_detector.py` — `.env` detection, secret pattern detection, `has_secrets` flagging
- `fcode/parser/python_ast.py` — Python AST parsing (no tree-sitter)
- `fcode/parser/symbol_extractor.py` — function/class/method/variable extraction
- `fcode/parser/import_extractor.py` — import extraction (ParsedImport with module_name, imported_names, alias, line_number)
- `fcode/parser/route_detector.py` — FastAPI/Flask route detection
- `fcode/graph/graph_builder.py` — code relationship extraction (nodes: file, function, class, method, route, import, test; edges: defines, imports, inherits, calls, tests, handles_route; variables produce no graph nodes)

**Required Tests (owned by Scanner/Parser Agent):**
- `tests/unit/test_file_scanner.py`
- `tests/unit/test_ignore_rules.py`
- `tests/unit/test_secret_detector.py`
- `tests/unit/test_python_ast.py`
- `tests/unit/test_symbol_extractor.py`
- `tests/unit/test_import_extractor.py`
- `tests/unit/test_route_detector.py`
- `tests/unit/test_graph_builder.py`
- `tests/fixtures/` — sample Python files

**Documentation Updates:**
- Update `docs/05_INDEXING_AND_RETRIEVAL.md` if parsing behavior changes

**Completion Report:**
```
## Completion Report — Scanner/Parser Agent

**Files changed:**
- list

**What was implemented:**
- file scanning, Python parsing, symbol extraction, graph building

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 10. Work Package 4: Chunking and Embeddings

**Agent Name:** Chunking/Embeddings Agent

**Goal:** Implement semantic chunk creation (Python, Markdown/RST, config) and local Sentence Transformers embeddings.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`
- `docs/05_INDEXING_AND_RETRIEVAL.md`

**Allowed Files/Folders:**
- `fcode/chunking/`
- `fcode/embeddings/`
- `fcode/contracts/` (read-only imports)

**Forbidden Files/Folders:**
- `fcode/parser/`
- `fcode/storage/`
- `fcode/mcp_server/`
- `fcode/dashboard/`
- `fcode/indexing/`
- `fcode/scanner/`
- `fcode/graph/`

**Dependencies:** Scanner/Parser Agent (needs parser output format — `ParsedFile`, `ParsedSymbol`, `ParsedRoute`)

**Expected Outputs:**
- `fcode/chunking/chunker.py` — semantic chunk creation (Python: file_summary, function, class, method, route, test; Markdown: readme_section by Markdown heading; RST: readme_section by RST section heading; Config: config chunks at 100-line blocks; Generic text: no chunks) with input validation (scanned/parsed file matching)
- `fcode/embeddings/encoder.py` — Sentence Transformers encoding (device='cpu', batch=100, dimension=384, local-only loading, no hardcoded cache path, per-chunk failure handling, embedding_count verification)

**Required Tests (owned by Chunking/Embeddings Agent):**
- `tests/unit/test_chunker.py`
- `tests/unit/test_encoder.py`

**Documentation Updates:**
- Update `docs/05_INDEXING_AND_RETRIEVAL.md` if chunking strategy changes

**Completion Report:**
```
## Completion Report — Chunking/Embeddings Agent

**Files changed:**
- list

**What was implemented:**
- chunking, embeddings

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 11. Work Package 5: Integration (7 steps)

### WP5 Step 1 — Complete

Step 1 established indexing contracts (`IndexCounts`, `IndexDiagnostic`, `IndexRunResult` with validation),
the pure `IndexStateMachine` (no I/O), and updated documentation. The indexing pipeline is not yet
implemented. See WP5 Step 1 report for full details.

### Remaining WP5 Steps

**Agent Name:** Integration Agent

**Goal:** Connect all pipeline modules into a working indexing pipeline. Implement `fcode/indexing/index_service.py` with the full Phase A/B/C state machine.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`
- `docs/03_SYSTEM_ARCHITECTURE.md`
- `docs/04_DATA_MODEL.md`
- `docs/05_INDEXING_AND_RETRIEVAL.md`

**Allowed Files/Folders:**
- `fcode/indexing/`
- `fcode/contracts/` (read-only imports)

**Forbidden Files/Folders:**
- `fcode/cli/`
- `fcode/storage/` (read-only calls through public interface)
- `fcode/parser/`
- `fcode/scanner/`
- `fcode/chunking/`
- `fcode/embeddings/`
- `fcode/graph/`
- `fcode/mcp_server/`
- `fcode/dashboard/`
- `fcode/retrieval/`

**Dependencies:** WP1 (CLI interface), WP2 (storage modules), WP3 (scanner, parser, graph builder), WP4 (chunker, encoder)

**Expected Outputs:**
- `fcode/indexing/__init__.py`
- `fcode/indexing/state_machine.py` — pure state controller (no I/O)
- `fcode/indexing/index_service.py` — pipeline orchestrator (later WP5 steps)

**`state_machine.py` contract:**
- `IndexStateMachine` — deterministic state machine with legal forward transitions and ERROR from every non-terminal state
- `InvalidIndexStateTransition` — exception for illegal transitions
- No I/O, no feature-module imports, no filesystem access
- Tracks: state, phase, completed_phase, history (immutable tuple), terminal flag, persistent_replacement_started flag
- Phase A: PENDING; Phase B: SCANNING through GRAPHING; Phase C begins at STORING

**`index_service.py` contract:**
- Orchestrates services only; contains no parser/storage/chunking algorithms
- Controls status transitions (pending → scanning → parsing → chunking → embedding → graphing → storing → complete)
- Controls active-status semantics (Phase A/B preserve existing complete index; Phase C begins destructive replacement)
- Executes cleanup rules on failure
- Maps fatal errors to the error catalog
- Owns the rebuild state machine (Phase A: preflight, Phase B: build in memory, Phase C: persistent replacement)
- Verifies counts before marking complete
- Does not call storage modules directly — calls through public interfaces
- Storage modules do not call each other

**Required Tests:** Cross-module integration tests owned by Tests Agent (WP6). Integration Agent verifies unit tests pass.

**WP5 Step 1 specific tests (owned by Integration Agent):**
- `tests/unit/test_index_state_machine.py` — 64 tests covering initial state, happy path, failure transitions, illegal transitions, public methods, and exception behavior

**WP5 Step 1 contract changes:**
- `IndexCounts` — appended parse_errors, symbols, embedding_eligible, embedding_skipped, embedding_failed, warnings, errors; added `validate()`
- `IndexDiagnostic` — added code, recoverable, repo_relative_path, details fields; phase made optional; added `validate()`
- `IndexRunResult` — state defaults to PENDING; phase defaults to None; added diagnostics list; added `validate()`

**Documentation Updates:**
- Update any doc if contracts changed during integration

**Completion Report:**
```
## Completion Report — Integration Agent

**Files changed:**
- list

**What was implemented:**
- pipeline orchestration, status transitions, cleanup

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 12. Work Package 6: First-Slice Tests

**Agent Name:** Tests Agent

**Goal:** Implement golden test repository, cross-module scenario tests, failure-cleanup tests, and acceptance-matrix tests.

**Required Docs:**
- `AGENTS.md` (Sections 1-22)
- `docs/01_CONTEXT.md`
- `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md`

**Allowed Files/Folders:**
- `tests/`

**Forbidden Files/Folders:**
- `fcode/` (no production code)

**Dependencies:** All WP1-WP5 (needs implemented code to test)

**Expected Outputs:**
- `tests/golden/` — golden test repository (FastAPI app structure)
- `tests/golden/test_scenarios.py` — scenario tests from `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md`
- `tests/integration/` — integration tests (cross-module, failure-cleanup)
- `tests/conftest.py` — shared fixtures

**The Tests Agent owns:**
- `tests/golden/`
- Cross-module integration tests
- Failure-cleanup tests
- Scenario-matrix tests
- Acceptance tests

**The Tests Agent may run but must not rewrite:**
- Feature-owned unit tests (those are owned by their respective feature agents)

**Required Tests:**
- All SC-IND-001 through SC-IND-040 from `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md`

**Documentation Updates:**
- Update `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md` if scenarios change

**Completion Report:**
```
## Completion Report — Tests Agent

**Files changed:**
- list

**What was implemented:**
- golden repo, scenario tests, integration tests

**What docs were updated:**
- list or "none"

**What tests/checks were run:**
- list

**Blockers:**
- issues or "none"

**Contract changes:**
- changes or "none"
```

---

## 13. Conflict Rules

1. **Same file, different agents:** The agent that needs the file more gets it; the other waits.
2. **Shared contract change:** Agent must stop, report with CHANGE-REQUEST, wait for approval.
3. **Database schema change:** Storage Agent owns schema; other agents propose changes.
4. **Tool schema change:** MCP Server Agent (deferred) owns tool definitions; other agents propose changes.
5. **Folder structure change:** Architecture decision; must be approved by project owner.

## 14. Test Ownership Summary

| Agent | Owned Test Files |
|-------|-----------------|
| CLI/Config Agent | `tests/unit/test_index_cmd.py`, `test_status_cmd.py`, `test_doctor_cmd.py`, `test_deferred_commands.py`, config/utility tests |
| Storage Agent | `tests/unit/test_sqlite_store.py`, `test_chroma_store.py`, `test_graph_store.py`, `test_fts_store.py` |
| Scanner/Parser Agent | `tests/unit/test_file_scanner.py`, `test_ignore_rules.py`, `test_secret_detector.py`, `test_python_ast.py`, `test_symbol_extractor.py`, `test_import_extractor.py`, `test_route_detector.py`, `test_graph_builder.py` |
| Chunking/Embeddings Agent | `tests/unit/test_chunker.py`, `test_encoder.py` |
| Tests Agent | `tests/golden/`, cross-module integration tests, failure-cleanup tests, scenario-matrix tests, acceptance tests |

## 15. Integration Sequence

```
Phase 0 (before Phase 1):
└── WP0: Contracts Agent

Phase 1 (parallel, after WP0):
├── WP1: CLI/Config Agent
├── WP2: Storage Agent
└── WP3: Scanner/Parser Agent

Phase 2 (after Phase 1):
└── WP4: Chunking/Embeddings Agent

Phase 3 (after Phase 2):
└── WP5: Integration Agent

Phase 4 (after Phase 3):
└── WP6: Tests Agent
```

## 16. Review Checklist

Before marking a work package as complete:
- [ ] All required files created/modified
- [ ] All required tests passing
- [ ] No files outside allowed folders modified
- [ ] No shared contracts changed without approval
- [ ] Documentation updated if contracts changed
- [ ] Completion report submitted
- [ ] No blocking issues remaining

## 17. Contract Change Process

If any implementation agent discovers a conflict with documented contracts:
1. Stop work immediately
2. Do not make the change
3. Submit a CHANGE-REQUEST using the format in `AGENTS.md` Section 18.2
4. Wait for approval before proceeding
5. No agent may silently modify schema, CLI, MCP tools, error codes, ownership, scope, or storage behavior
