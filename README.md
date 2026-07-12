<div align="center">

# F Code

**Local-first repository intelligence for AI coding agents.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-400%20passed-brightgreen.svg)](#testing)
[![Status](https://img.shields.io/badge/status-first%20slice%20complete-orange.svg)](#development-status)

F Code indexes a Python repository on your laptop, extracts code relationships, stores them locally, and exposes search and planning tools through MCP — so coding agents can find existing implementations before writing new ones, all without sending code anywhere.

[Getting Started](#quick-start) &middot; [Commands](#commands) &middot; [Architecture](#architecture) &middot; [Documentation](#documentation) &middot; [License](#license)

</div>

---

## Why F Code

When a coding agent works on an unfamiliar repository, it doesn't know what already exists. It may reimplement functions, create redundant files, or suggest changes that break related code.

F Code solves this by giving agents a **local intelligence layer** that answers "does this already exist?" before they write code.

| Problem | F Code Solution |
|---------|----------------|
| Reimplements existing functions | Finds and suggests reusing existing code |
| Creates new files when old ones should be extended | Surfaces related files with evidence |
| Suggests breaking changes | Maps code relationships and impact |
| Ignores existing test coverage | Discovers related tests automatically |
| Works blindly on unfamiliar repos | Provides repository wiki and structure |

## Features

- **Full Python Indexing** — scan, parse, chunk, embed, and build a code graph
- **MCP Tool Interface** — `search_code`, `find_symbol`, `check_existing_implementation`, and more for coding agents
- **Code Graph** — nodes and edges for functions, classes, methods, routes, imports, and tests
- **Hybrid Retrieval** — semantic vector search + keyword search + exact symbol lookup + graph traversal
- **Secret Detection** — automatically detects and redacts API keys, tokens, and passwords
- **Ignore Rules** — respects `.gitignore`, `.fcodeignore`, and hardcoded exclusions
- **Local Dashboard** — Streamlit UI for human inspection (localhost only)
- **Privacy First** — all indexing, storage, and search runs locally; no code leaves your machine

## Quick Start

```bash
# Install from source
git clone https://github.com/your-org/ai-codebase-onboarding-agent.git
cd ai-codebase-onboarding-agent
pip install -e .

# Index a repository
fcode index /path/to/your/repo

# Check index status
fcode status /path/to/your/repo

# Verify environment health
fcode doctor
```

### Development Install

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Commands

| Command | Description | Status |
|---------|-------------|--------|
| `fcode index [repo]` | Perform a full local rebuild and safely promote it | Functional |
| `fcode status [repo]` | Show the active complete generation status and counts | Functional |
| `fcode doctor` | Check dependencies and environment health | Functional |
| `fcode dashboard` | Start Streamlit dashboard on localhost | Planned (WP6) |
| `fcode mcp --repo <repo>` | Start MCP stdio server for coding agents | Planned (WP6) |
| `fcode setup <agent> --repo <repo>` | Configure agent integration | Planned (WP6) |

## Architecture

```
fcode/
├── cli/              # Typer CLI commands
│   └── commands/     # index, status, doctor, dashboard, mcp, setup
├── config/           # Settings and defaults
├── contracts/        # Shared enums, models, error codes, protocol interfaces
├── scanner/          # File discovery, ignore rules, secret detection
├── parser/           # Python AST parsing, symbol/import/route extraction
├── graph/            # Code graph construction (nodes + edges)
├── storage/          # Persistence layer
│   ├── sqlite_store.py    # SQLite metadata + CHECK constraints
│   ├── graph_store.py     # Graph node/edge persistence
│   ├── fts_store.py       # FTS5 full-text search
│   ├── chroma_store.py    # Vector embeddings
│   └── migrations/        # Schema versioning
└── utils/            # Health checks, shared utilities
```

### Data Flow

```
Repository
    │
    ▼
┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│ Scanner │───▶│ Parser  │───▶│ Chunker  │───▶│ Encoder │───▶│ Storage  │
│         │    │         │    │          │    │         │    │          │
│ ignore  │    │ AST     │    │ split    │    │ 384-dim │    │ SQLite   │
│ secrets │    │ symbols │    │ by type  │    │ vectors │    │ Chroma   │
│ symlinks│    │ imports │    │          │    │ local   │    │ FTS5     │
│ binary  │    │ routes  │    │          │    │         │    │ Graph    │
└─────────┘    └─────────┘    └──────────┘    └─────────┘    └──────────┘
```

### Code Graph

| Node Types | Edge Types | Confidence Labels |
|------------|------------|-------------------|
| `file` | `defines` | `EXTRACTED` |
| `function` | `imports` | `INFERRED` |
| `class` | `inherits` | `AMBIGUOUS` |
| `method` | `calls` | |
| `route` | `tests` | |
| `import` | `handles_route` | |
| `test` | | |

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.10+ | Type safety, modern stdlib |
| CLI | Typer + Rich | Clean CLI with formatted output |
| Vectors | Chroma (local) | Persistent, no Docker |
| Embeddings | Sentence Transformers (`all-MiniLM-L6-v2`) | Local, 384-dim, no API |
| Metadata | SQLite + FTS5 | Embedded, no server |
| Code Graph | Native Python + SQLite recursive CTE | Lightweight, SQL-native traversal |
| Parsing | Python `ast` | Built-in, reliable |
| Testing | pytest | Fast, extensible |
| Dashboard | Streamlit | Local web UI |
| MCP | MCP Python SDK (stdio) | Agent integration standard |

## Privacy & Security

- **All local** — indexing, storage, retrieval, and tool serving run on your machine
- **No code uploads** — repository source never leaves your laptop
- **No LLM APIs** — embeddings generated locally with Sentence Transformers
- **Secret detection** — `.env` files, API keys, and tokens are detected and redacted
- **No MCP writes** — MCP tools are read-only and planning-only
- **No network exposure** — MCP server uses stdio transport; dashboard is localhost only

## Repository Limits

| Limit | Value | Behavior |
|-------|-------|----------|
| Max eligible files | 10,000 | Abort with exit code 1 |
| Max total content | 50 MiB | Abort with exit code 1 |
| Max file size | 1 MiB | Skip file, continue indexing |

## Testing

```bash
# Run full suite (973+ tests)
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=fcode --cov-report=term-missing

# Run specific module tests
python -m pytest tests/unit/test_sqlite_store.py -v
python -m pytest tests/unit/test_graph_builder.py -v
python -m pytest tests/unit/test_wp3_contract_compatibility.py -v
```

### Test Coverage

| Module | Tests | What's Covered |
|--------|------:|----------------|
| CLI / Bootstrap | 65 | Commands, entry points, config, subprocess behavior |
| Contracts | 36 | Enums, models, error codes, protocol interfaces |
| Storage | 168 | SQLite, Chroma, FTS5, graph store, schema compatibility |
| Scanner | 44 | File discovery, ignore rules, secret detection |
| Parser | 56 | AST, symbols, imports, routes, Python parsing |
| Graph | 19 | Graph building, node/edge construction |
| WP3 Compatibility | 42 | Cross-module contract alignment |
| Indexing/Integration | 543 | State machine, scan-parse-chunk, embed-graph, SQLite/FTS, full rebuild, CLI/status |
| **Total** | **973** | **All passing, 0 failures** |

## Documentation

| File | Purpose |
|------|---------|
| `AGENTS.md` | Root rule file for all coding agents |
| `docs/01_CONTEXT.md` | Master context and locked decisions |
| `docs/02_PRODUCT_SPEC.md` | Product specification |
| `docs/03_SYSTEM_ARCHITECTURE.md` | System architecture |
| `docs/04_DATA_MODEL.md` | Storage and data model |
| `docs/05_INDEXING_AND_RETRIEVAL.md` | Indexing and retrieval pipeline |
| `docs/06_MCP_TOOLS_CONTRACT.md` | MCP tool schemas and contracts |
| `docs/07_DASHBOARD_SPEC.md` | Streamlit dashboard specification |
| `docs/08_SCENARIOS_AND_ACCEPTANCE_TESTS.md` | Test scenarios and acceptance criteria |
| `docs/09_AGENT_TASKS.md` | Parallel agent work packages |

## Development Status

**First-slice implementation complete.** All core modules are built and verified:

- WP1 (CLI & Config) — CLI entry point, commands, configuration, health checks
- WP2 (Storage) — SQLite schema, Chroma vectors, FTS5 search, graph persistence
- WP3 (Scanner, Parser, Graph) — file scanning, Python AST parsing, code graph construction
- WP4 (Chunking, Embeddings) — semantic chunk creation, local Sentence Transformers encoding
- WP5 (Integration) — full pipeline orchestration, state machine, complete safe rebuilds, CLI index/status
- 973 tests passing across all modules

**Planned for next slice:**
- WP6 — Dashboard, MCP server, setup commands, retrieval, end-to-end tests

## License

MIT

---

<div align="center">

Built for developers who believe code intelligence should be local, private, and fast.

</div>
