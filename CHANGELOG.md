# Changelog

All notable changes to DeepOrra are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MIT License and project logo

### Changed

- Full README rewrite with architecture diagram, quick-start guide, and usage documentation

---

## [0.1.0] - 2026-07-14

*Release date placeholder — will be updated when the v0.1.0 tag is created.*

### Added

- **CLI commands:** `deeporra index` (full repository indexing pipeline), `deeporra status` (active index state and counts), `deeporra doctor` (environment health diagnostics), `deeporra mcp` (MCP stdio server), `deeporra dashboard` (Streamlit dashboard)
- **Deferred command stub:** `deeporra setup` — prints a notice and exits with code 2
- **Indexing pipeline:** scan → parse → chunk → embed → graph → persist with atomic generation promotion and rollback on failure
- **Repository scanner:** file discovery, `.gitignore`-style rule support, secret detection and redaction, file eligibility enforcement (10,000-file and 50 MiB limits)
- **Python AST parser:** symbol extraction (functions, classes, methods), import graph extraction, HTTP route detection (Flask/FastAPI patterns), parse-error resilience
- **Code graph:** file–symbol, import, route, and test-relationship edges persisted in SQLite `code_nodes`/`code_edges` tables
- **Semantic chunking:** code-aware chunker that preserves structure around functions and classes
- **Local embeddings:** Sentence Transformers encoder (`all-MiniLM-L6-v2`, 384 dimensions) with batched encoding, retry logic, and offline operation
- **Persistent storage:**
  - SQLite store with schema migrations (metadata, status, index state)
  - Chroma vector store for semantic search
  - FTS5 full-text search index for keyword search
  - Graph store for code-relationship queries
- **Query service:** unified read interface for search (text, semantic, hybrid), symbols, routes, related code, and change-impact analysis
- **Repository input preparation:** local folder, public GitHub repository, and ZIP archive sources
- **MCP server (read-only, stdio):** eight planning tools for AI coding agents — `repository_summary`, `search_code`, `hybrid_search`, `find_symbols`, `find_routes`, `get_related_code`, `analyze_change_impact`, `find_existing_implementation`
- **Streamlit dashboard:** localhost-only human-inspection UI for indexed repositories (code search, symbol/route browsing, graph exploration, impact analysis)
- **Configuration system:** YAML-based repository config (`.deeporra/config.yml`) with per-repository settings
- **Health checks:** Python version, required imports, SQLite FTS5 availability, local embedding model presence, directory writability, config parsing
- **Golden test suite:** WP6 golden-repository matrix with semantic manifests for exact oracle comparison (symbols, chunks, graph, parse status)

### Changed

- **Rebranded** from *F Code* to *DeepOrra*: all module paths, package names, documentation, and internal references updated
- **Simplified project structure:** removed dead code (unused `fcode/` paths, deprecated contract fields) and unified module layout under `deeporra/`
- **Contract freeze enforced:** persisted schema, CLI interface, MCP tool schema, and error vocabulary locked for the first-slice build
- **Repository index storage moved** to `.deeporra/` inside each indexed repository

### Fixed

- Deterministic graph record IDs for reproducible index generations
- Doctor diagnostics aligned with offline indexing requirements (no model download during check)
- Indexing process-control exception propagation during multi-stage rebuild
- Exact staged FTS verification and active-status count preservation
- Embedding encoder protocol contract alignment and oversized-data handling
- CLI subprocess test paths (`.` replaced with nonexistent path for isolation)
- MCP hybrid search stall resolution
- WP5 CLI safety guarantees and repository CLI configuration honoring
- WP6 golden fixture integrity and oracle reconciliation (symbol, chunk, graph, parse-status)

### Security

- Secret detection and redaction during scanning (no secrets persisted to index)
- Sensitive files (`.env`, credential patterns) excluded from indexing
- All MCP tools are read-only: no file writes, shell execution, or network access
- Dashboard bound to localhost only

### Removed

- Legacy `fcode/` package directory (fully migrated to `deeporra/`)
- Deprecated contract fields and interfaces from the pre-freeze prototype
- Dead code identified during the simplification pass (unused wrappers, stale test fixtures)

### Known Limitations

- Python-only AST parsing (multi-language support deferred)
- No incremental indexing — each `index` run performs a full rebuild
- One-hop graph traversal only (`get_related_code` depth limited to 1)
- `analyze_change_impact` shows first-order relationships only (no transitive analysis)
- MCP tools are read-only and planning-only — no automatic source editing
- No private repository authentication
- No hosted SaaS — local-first only
- No CI/CD integration
- Windows-tested only — macOS and Linux not yet validated in this release

[Unreleased]: #
[0.1.0]: #
