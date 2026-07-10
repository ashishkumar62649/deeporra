# 07_DASHBOARD_SPEC.md — F Code Dashboard Specification

## 1. Dashboard Purpose

The F Code dashboard is a local Streamlit application for human inspection. It helps users:
- See what F Code indexed
- Browse repository structure and wiki
- Test queries manually
- Preview what MCP tools return
- Understand repository relationships

The dashboard is NOT the primary interface. The MCP tools for coding agents are the primary interface. The dashboard is a human inspection and debugging tool.

## 2. Dashboard Principles

1. **Localhost only** — No network exposure. Runs on `localhost:8501`.
2. **Human inspection** — Not the agent interface. Helps humans understand what agents see.
3. **Simple and direct** — No complex SaaS UI. No login. No accounts.
4. **Evidence-focused** — Every result shows file paths, symbols, line ranges.
5. **Privacy-aware** — Never shows secret content. Redacted values shown as `[REDACTED]`.

## 3. Localhost-Only Current Build

The dashboard binds to `127.0.0.1:8501`. No configuration for remote access. No authentication. No HTTPS. Local use only.

## 4. Main User Flow

```
1. User runs: fcode dashboard
2. Browser opens to localhost:8501
3. User sees Connect Repository page
4. User enters GitHub URL or uploads ZIP
5. F Code indexes the repository
6. User navigates to Repository Wiki page
7. User browses structure, symbols, summary
8. User navigates to Ask Repository page
9. User asks questions, sees evidence
10. User navigates to Agent Tools Preview
11. User tests MCP tools manually
```

## 5. Pages

| Page | Purpose | Key Components |
|------|---------|----------------|
| 1. Connect Repository | Add repository for indexing | URL input, ZIP upload, index button |
| 2. Indexing Status | View indexing progress and results | Progress bar, stats, error messages |
| 3. Repository Wiki | Browse repository structure | Tree view, symbols, summary, routes |
| 4. Ask Repository | Ask questions, see evidence | Question input, answer display, evidence cards |
| 5. Agent Tools Preview | Test MCP tools manually | Tool selector, input form, output display |

## 6. Page 1: Connect Repository

**Purpose:** Add a repository for indexing.

**Components:**
- GitHub URL input field
- ZIP file upload button
- "Index Repository" button
- Recently indexed repositories list

**Behavior:**
1. User enters GitHub URL or uploads ZIP
2. Click "Index Repository"
3. System clones/extracts repository
4. Indexing begins (shows progress on Page 2)
5. After indexing, redirects to Page 3 (Repository Wiki)

**Empty state:** "Enter a GitHub URL or upload a ZIP file to get started."

**Error states:**
- Invalid GitHub URL: "Please enter a valid GitHub repository URL."
- Repository too large: "Repository exceeds size limit. Try a smaller repository."
- Indexing failed: "Indexing failed. Check the error details below."

## 7. Page 2: Indexing Status

**Purpose:** View indexing progress and results.

**Components:**
- Progress bar (0-100%)
- Current step display (scanning, parsing, chunking, embedding, graphing)
- Statistics table
- Error log (if any)
- "Reindex" button

**Statistics displayed:**
| Metric | Value |
|--------|-------|
| Total files | N |
| Indexed files | N |
| Symbols extracted | N |
| Chunks created | N |
| Graph edges | N |
| Embedding model | all-MiniLM-L6-v2 |
| Index size | N MB |
| Time taken | N seconds |

**Empty state:** "No repository indexed yet. Go to Connect Repository to start."

**Error state:** Show error message with details and "Retry" button.

## 8. Page 3: Repository Wiki

**Purpose:** Browse repository structure and understand the codebase.

**Sections:**

### 8.1 Project Summary
- Repository name
- Detected language/framework
- Total files, symbols, chunks
- Entry points (main files)
- Summary text (from README or file analysis)

### 8.2 Folder Structure
- Tree view of repository folders
- File counts per folder
- Clickable to see files in each folder

### 8.3 Important Files
- Files with most symbols
- Entry point files
- Configuration files
- Test files

### 8.4 Major Symbols
- Functions with most connections (god nodes)
- Classes with most methods
- Most-called functions

### 8.5 Route Summary (if FastAPI/Flask detected)
- All API routes
- HTTP methods
- Handler functions

### 8.6 Test Summary
- Test files found
- Test functions count
- Coverage areas

### 8.7 Suggested Questions
- "Where is authentication handled?"
- "How is the database configured?"
- "What are the main entry points?"
- "Where are tests located?"

**Empty state:** "Repository not indexed. Go to Connect Repository to start."

## 9. Page 4: Ask Repository

**Purpose:** Ask natural language questions about the repository.

**Components:**
- Question input field
- "Ask" button
- Answer display area
- Evidence cards
- Retrieval method indicator
- Confidence indicator

**Behavior:**
1. User types question
2. Click "Ask" or press Enter
3. System retrieves relevant code
4. Displays answer with evidence
5. Shows file paths, symbols, line ranges
6. Shows confidence level

**Evidence card format:**
```
File: app/utils/validators.py
Symbol: validate_email (function)
Lines: 42-68
Confidence: EXTRACTED
Relevance: 92%
Reason: Function validates email format
```

**Empty state:** "Ask a question about the repository. Try: 'Where is authentication handled?'"

**Error states:**
- No results: "No matching code found for your question."
- Index not ready: "Repository not indexed yet."

## 10. Page 5: Agent Tools Preview

**Purpose:** Test MCP tools manually to see what coding agents will see.

**Components:**
- Tool selector dropdown
- Dynamic input form (changes based on selected tool)
- "Run Tool" button
- Output display (JSON formatted)
- Response time indicator

**Supported tools for preview:**
1. `check_existing_implementation` — input: feature description
2. `find_symbol` — input: symbol name
3. `explain_change_impact` — input: file path, function name
4. `plan_minimal_change` — input: task description
5. `search_code` — input: query string
6. `find_related_files` — input: file path
7. `find_related_tests` — input: file or function name
8. `get_file_context` — input: file path

**Output format:** Pretty-printed JSON with syntax highlighting.

**Empty state:** "Select a tool and enter parameters to see what coding agents will see."

## 11. Shared UI Components

### Evidence Card
Displays a single code reference with:
- File path (clickable)
- Symbol name and type
- Line range
- Confidence badge
- Relevance score
- Content preview

### File Viewer
Displays file content with:
- Syntax highlighting
- Line numbers
- Symbol highlighting
- Clickable line references

### Status Badge
Displays indexing status with color:
- Green: complete
- Yellow: indexing
- Red: error
- Gray: pending

### Confidence Badge
Displays confidence level:
- Green: EXTRACTED
- Yellow: INFERRED
- Orange: AMBIGUOUS

## 12. Empty States

Every page must have a clear empty state message explaining:
- What the page does
- What the user should do next
- Example inputs where helpful

## 13. Error States

Every error must show:
- What went wrong
- Why it happened (if known)
- What the user can do to fix it
- Technical details (collapsed, for debugging)

## 14. Loading States

Every action must show:
- Progress indicator
- Current step description
- Estimated time remaining (if available)
- Cancel button (for long operations)

## 15. Evidence Display

Evidence is the most important UI element. Every result must show:
- File path (relative to repo root)
- Symbol name
- Line range (start-end)
- Confidence level (EXTRACTED/INFERRED/AMBIGUOUS)
- Relevance score (0-100%)
- Why this result was selected
- Content preview (first 3-5 lines)

## 16. File/Symbol Display

Files and symbols should be displayed with:
- Full path (truncated in list view, full in detail view)
- Language badge
- File type badge (source, test, config, doc)
- Symbol type icon
- Line count
- Connection count (how many other files/symbols reference this)

## 17. MCP Preview Display

MCP tool results should be displayed as:
- Pretty-printed JSON (collapsible)
- Summary at the top
- Evidence cards below
- Response time
- Tool name and input parameters (for reference)

## 18. Privacy Messaging

The dashboard must show privacy notices:
- "All data is stored locally on your machine"
- "No code is sent to external services"
- "MCP tools are read-only"
- "Secrets are detected and redacted"

## 19. Out-of-Scope UI

The dashboard does NOT include:
- Login/authentication
- User accounts
- Team features
- Remote access
- Graph visualization (network diagrams) — text-based wiki only
- Code editing
- Patch application
- Terminal/console access

## 20. Locked Dashboard Decisions

1. **Multiple repositories:** One repository at a time, switch via sidebar.
2. **Graph visualization:** Not in current build; text-based tree is sufficient.
3. **Pipeline stages:** Show combined results, not individual pipeline stages.
4. **Caching:** Always query fresh; index changes are reflected immediately.
5. **Configurable port:** Configurable via CLI flag `--port`, default 8501.
