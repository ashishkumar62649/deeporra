# 02_PRODUCT_SPEC.md — F Code Product Specification

## 1. Product Overview

F Code is a local repository intelligence tool that helps AI coding agents avoid writing code that already exists. It indexes a repository, extracts code relationships, and exposes search and planning tools through MCP so agents can check for existing implementations before writing new code.

## 2. Product Thesis

"F Code helps AI coding agents avoid writing code that already exists by giving them local, evidence-backed repository intelligence before implementation."

## 3. Target Users

**Primary:** Developers using AI coding agents who want those agents to be repository-aware.

**Secondary:** Human developers who want to inspect a repository's structure and reuse opportunities.

## 4. Primary User: AI Coding Agent User

This developer:
- Uses Claude Code, Codex, OpenCode, Cursor, Gemini CLI, or similar
- Works on unfamiliar repositories
- Wants the agent to find existing code before writing new code
- Cares about privacy (code stays local)
- Wants evidence-backed suggestions, not guesses

## 5. Secondary User: Human Developer

This developer:
- Wants to understand a repository's structure
- Wants to see what functions/classes exist and where
- Wants to test queries manually
- Wants to preview what coding agents will see
- Uses the Streamlit dashboard

## 6. Core Problem

When a coding agent works on an unfamiliar repository, it does not know what already exists. It may:
- Reimplement a function that exists in another module
- Create a new file when an existing file should be extended
- Suggest changes that break related code
- Ignore existing tests that cover the area being changed

## 7. Main Promise

F Code gives coding agents repository intelligence before they write code, so they:
- Find and reuse existing implementations
- Recommend modifications to existing files over new file creation
- Understand impact before suggesting changes
- Provide evidence (file paths, symbols, line ranges) with every suggestion

## 8. Current Build User Journey

```
1. Developer installs F Code: pip install fcode
2. Developer indexes a repository: fcode index /path/to/repo
3. F Code scans, parses, embeds, builds graph — stores in .fcode/
4. Developer opens dashboard: fcode dashboard
5. Developer inspects repository wiki, tests queries
6. Developer connects MCP server to coding agent: fcode mcp --repo /path/to/repo
7. Coding agent uses MCP tools to check before writing code
8. Agent calls check_existing_implementation("email validation")
9. F Code returns: "validate_email already exists in utils/validators.py:42"
10. Agent reuses existing code instead of creating duplicate
```

## 9. Human Dashboard Journey

```
1. User runs: fcode dashboard
2. Streamlit opens on localhost:8501
3. User enters GitHub URL or uploads ZIP
4. F Code indexes the repository
5. User sees repository wiki: structure, symbols, summary
6. User asks: "Where is authentication handled?"
7. Dashboard shows: relevant files, functions, evidence
8. User tests MCP tools manually
9. User sees what coding agents will see
```

## 10. Coding Agent MCP Journey

```
1. Agent starts with: fcode mcp --repo /path/to/repo
2. F Code starts MCP stdio server
3. Agent receives tool list from MCP
4. Agent receives coding task: "Add email validation"
5. Agent calls: check_existing_implementation({"feature": "email validation"})
6. F Code returns: existing implementation found in utils/validators.py
7. Agent calls: find_symbol({"name": "validate_email"})
8. F Code returns: function signature, file, line range, usage examples
9. Agent calls: plan_minimal_change({"target": "extend validate_email"})
10. F Code returns: minimal change plan with evidence
11. Agent implements change using existing code
```

## 11. Core Features

| Feature | Description | Priority |
|---------|-------------|----------|
| Repository indexing | Scan, parse, embed, build graph | Current build |
| Duplicate prevention | Check if implementation exists before writing | Current build |
| Symbol search | Find functions, classes, methods by name | Current build |
| Semantic search | Find code by natural language description | Current build |
| Impact analysis | Understand what breaks if a file changes | Current build |
| Minimal change planning | Recommend smallest change to existing files | Current build |
| Test discovery | Find related tests for a function/module | Current build |
| Repository wiki | Human-readable structure overview | Current build |
| MCP tools | Read-only tools for coding agents | Current build |
| Local dashboard | Streamlit UI for human inspection | Current build |

## 12. Non-Goals

| Non-Goal | Reason |
|----------|--------|
| Multi-language parsing | Python only in current build |
| Private repo auth | Public repos and ZIP only |
| Automatic patching | Read-only/planning-only |
| Cloud deployment | Local-first only |
| React frontend | Streamlit is sufficient |
| Team features | Single-user local tool |
| PR review | Out of current build scope |
| Architecture diagrams | Out of current build scope |

## 13. Differentiation

### F Code vs Graphify

| Aspect | F Code | Graphify |
|--------|--------|----------|
| Primary purpose | Help coding agents avoid duplicate code | Build knowledge graphs from code |
| Interface | MCP tools for agents + dashboard for humans | CLI + assistant skill |
| Storage | SQLite + Chroma | NetworkX graph + files |
| Retrieval | Hybrid vector + keyword + graph | Graph traversal only |
| Output | Evidence-backed answers, plans, impact | Interactive graph, report |
| Runtime dependency | No | No (for F Code) |

**Honest claim:** F Code focuses on local pre-write reuse checks for coding agents. Graphify focuses on building visual knowledge graphs. They solve different problems.

### F Code vs Ponytail

| Aspect | F Code | Ponytail |
|--------|--------|----------|
| Primary purpose | Repository intelligence for agents | Minimal-change discipline for agents |
| Category | RAG application | Agent behavior plugin |
| What it does | Indexes code, answers questions | Constrains how agents write code |
| Storage | SQLite + Chroma | None |
| Interface | MCP tools | Prompt rules + skills |

**Honest claim:** F Code gives agents knowledge about a repository. Ponytail gives agents discipline about writing code. F Code embeds Ponytail-style rules into its planning prompts.

### F Code vs Code Wiki Tools

| Aspect | F Code | Code Wiki Tools |
|--------|--------|----------------|
| Primary purpose | Agent intelligence layer | Generated documentation |
| Focus | Pre-write reuse checks | Post-write documentation |
| Interface | MCP tools for agents | Generated markdown/HTML |
| Retrieval | Hybrid search + graph | Document search |

**Honest claim:** F Code is for agents that are about to write code. Code wiki tools are for humans who want to read documentation. Different audiences, different timing.

## 14. Graphify Comparison

F Code does NOT compete with Graphify. F Code borrows design ideas from Graphify:
- Node/edge schema: `{id, label, source_file, source_location}` + `{source, target, relation, confidence}`
- Confidence labels: EXTRACTED / INFERRED / AMBIGUOUS
- File detection and filtering patterns

F Code does NOT:
- Use Graphify as a dependency
- Build interactive graph visualizations
- Export to Obsidian, Neo4j, or FalkorDB
- Process media files (images, video)

## 15. Ponytail Comparison

F Code does NOT compete with Ponytail. F Code embeds Ponytail-style rules into its agent prompts:
- 7-rung minimal solution ladder
- "No abstractions not requested"
- "Deletion over addition"
- Root-cause debugging approach

F Code does NOT:
- Install Ponytail as a dependency
- Replace Ponytail's agent behavior plugin
- Modify how external coding agents behave (only provides intelligence tools)

## 16. Code Wiki-Style Comparison

F Code is NOT a code wiki generator. F Code:
- Indexes code for agent consumption, not human documentation
- Provides MCP tools for real-time queries, not static reports
- Focuses on duplicate prevention, not documentation generation
- Stores structured metadata, not rendered markdown

## 17. Success Criteria

| Criterion | Measurable Target |
|-----------|-------------------|
| Finds existing reusable functions | 90%+ hit rate on golden scenarios |
| Reduces duplicate code suggestions | 80%+ duplicate prevention rate |
| Recommends existing files before new files | 85%+ reuse recommendation rate |
| Shows evidence with file paths and symbols | 100% of answers include evidence |
| Gives minimal-change plans | 80%+ plans modify existing files |
| Answers from local index | 100% local, no external API calls |
| Keeps repository code private | 0 code uploads to external servers |
| Works through MCP tools | All 8 tools functional |
| Provides human-readable wiki | Dashboard shows repository structure |

## 18. Failure Criteria

The project fails if:
- F Code cannot find existing reusable code in golden test scenarios
- F Code suggests creating new files when existing files should be extended
- F Code's MCP tools are too slow to be useful (>10s per query)
- F Code leaks repository code to external services
- F Code's index is unreliable (frequent missing/incorrect results)
- F Code cannot parse standard Python projects

## 19. Current Build Acceptance Criteria

The current build is acceptable if:
1. `fcode index <repo>` completes without errors for Python repos up to 10,000 files
2. `fcode mcp --repo <repo>` starts and responds to all 8 MCP tools
3. `fcode dashboard` shows repository wiki and tool preview
4. `check_existing_implementation` finds existing functions with 80%+ accuracy
5. `find_symbol` returns correct file, line range, and signature
6. `search_code` returns relevant results for natural language queries
7. `plan_minimal_change` recommends modifying existing files over new creation
8. All data stays local (no network calls during operation)
9. No secrets or `.env` content appears in index or reports

## 20. Open Questions

1. Should the dashboard show graph visualization (network diagram) in the current build? (Recommended: no, text-based wiki is sufficient.)
2. Should F Code support monorepos in the current build? (Recommended: single repository per index.)
3. Should the MCP server support multiple repositories simultaneously? (Recommended: one repo per MCP server instance in current build.)
4. Should generated reports be cached or regenerated on each query? (Recommended: cached, invalidated on reindex.)
