# 08_SCENARIOS_AND_ACCEPTANCE_TESTS.md — F Code Scenarios and Acceptance Tests

## 1. Purpose

This document stress-tests the F Code product before coding. It defines scenarios that F Code must pass to prove it is useful. This is one of the most important documents.

## 2. Product Success Hypothesis

"F Code is successful if it helps a coding agent find and reuse existing code before creating duplicate code."

## 3. Product Failure Hypothesis

"F Code fails if it cannot identify existing reusable code, suggests new files when existing files should be reused, or provides evidence-free answers."

## 4. Scenario Format

Each scenario includes:
- **Scenario ID:** Unique identifier
- **User/Agent Input:** What the user or agent asks
- **Starting Condition:** Repository state before the test
- **Expected F Code Behavior:** What F Code should do
- **Expected Output:** Specific tool/dashboard output
- **Required Evidence:** File paths, symbols, line ranges
- **Pass Condition:** Measurable success criteria
- **Fail Condition:** Measurable failure criteria

## 5. Golden Test Repository Requirements

A golden test repository must exist with:
- FastAPI application structure
- Authentication module (`app/auth/`)
- User module (`app/users/`)
- Validation utilities (`app/utils/validators.py`)
- Email service (`app/services/email_service.py`)
- Tests (`tests/`)
- Configuration files
- README

This repository is used for all scenarios unless otherwise noted.

## 6. Deferred Human Dashboard Scenarios

### SC-DASH-001: Repository Wiki Display

**Input:** User opens dashboard after indexing
**Starting Condition:** Repository is indexed
**Expected Behavior:** Dashboard shows Repository Wiki page
**Expected Output:**
- Project summary with language/framework
- Folder structure tree
- List of important files
- Major symbols (functions, classes)
- Route summary (if FastAPI)
- Test summary

**Pass Condition:** Wiki shows at least 5 important files, 10 symbols, and accurate folder structure
**Fail Condition:** Wiki shows empty or incorrect information

---

### SC-DASH-002: Ask Repository Question

**Input:** User asks "Where is authentication handled?"
**Starting Condition:** Repository is indexed
**Expected Behavior:** Dashboard returns relevant files and symbols
**Expected Output:**
- Files: `app/auth/login.py`, `app/auth/middleware.py`
- Symbols: `login_user`, `authenticate_token`
- Line ranges for each
- Confidence: EXTRACTED

**Pass Condition:** Results include at least 2 authentication-related files
**Fail Condition:** Results are empty or unrelated to authentication

---

### SC-DASH-003: Agent Tools Preview

**Input:** User selects `check_existing_implementation` tool, enters "email validation"
**Starting Condition:** Repository is indexed
**Expected Behavior:** Tool returns existing implementation
**Expected Output:**
- `existing: true`
- Match: `validate_email` in `app/utils/validators.py`
- Line range: 42-68
- Reuse suggestion

**Pass Condition:** Tool identifies existing `validate_email` function
**Fail Condition:** Tool returns no results or incorrect results

---

### SC-DASH-004: Indexing Status Display

**Input:** User views Indexing Status page during indexing
**Starting Condition:** Indexing in progress
**Expected Behavior:** Progress bar updates, statistics display
**Expected Output:**
- Progress bar at 50%+
- Current step: "embedding" or "graphing"
- Statistics: files found, symbols extracted

**Pass Condition:** Progress is visible and accurate
**Fail Condition:** No progress display or incorrect statistics

---

## 7. Deferred MCP Coding Agent Scenarios

### SC-MCP-001: Check Existing Implementation (Email Validation)

**Agent Input:** `check_existing_implementation({"feature": "email validation"})`
**Starting Condition:** Repository contains `validate_email` in `app/utils/validators.py`
**Expected Output:**
```json
{
  "existing": true,
  "confidence": "EXTRACTED",
  "matches": [{
    "file_path": "app/utils/validators.py",
    "symbol_name": "validate_email",
    "start_line": 42,
    "end_line": 68,
    "can_reuse": true
  }]
}
```

**Pass Condition:** Finds existing `validate_email` with correct file and line range
**Fail Condition:** Returns `existing: false` or wrong file

---

### SC-MCP-002: Check Existing Implementation (JWT Token)

**Agent Input:** `check_existing_implementation({"feature": "JWT token creation"})`
**Starting Condition:** Repository contains `create_token` in `app/auth/tokens.py`
**Expected Output:**
- `existing: true`
- Match: `create_token` in `app/auth/tokens.py`

**Pass Condition:** Finds existing token creation function
**Fail Condition:** Returns no results

---

### SC-MCP-003: Find Symbol

**Agent Input:** `find_symbol({"name": "login_user"})`
**Starting Condition:** Repository contains `login_user` function
**Expected Output:**
- Symbol found with file path, line range, signature
- Callers and callees listed

**Pass Condition:** Returns correct file, lines, and relationships
**Fail Condition:** Symbol not found or wrong location

---

### SC-MCP-004: Explain Change Impact

**Agent Input:** `explain_change_impact({"target": "app/auth/login.py", "change_type": "modify_function", "function_name": "login_user"})`
**Starting Condition:** `login_user` is called by `app/api/auth.py`
**Expected Output:**
- Direct callers listed
- Affected tests listed
- Risk level: medium
- Safe change strategy

**Pass Condition:** Identifies `app/api/auth.py` as direct caller
**Fail Condition:** Misses callers or tests

---

### SC-MCP-005: Plan Minimal Change

**Agent Input:** `plan_minimal_change({"task": "Add email validation to registration"})`
**Starting Condition:** `validate_email` exists in `app/utils/validators.py`, registration endpoint in `app/api/auth.py`
**Expected Output:**
- Plan: modify `app/api/auth.py` to import and call `validate_email`
- No new files needed
- Existing code to reuse: `validate_email`

**Pass Condition:** Recommends modifying existing file, not creating new file
**Fail Condition:** Recommends creating new validation file

---

### SC-MCP-006: Find Related Tests

**Agent Input:** `find_related_tests({"target": "app/utils/validators.py"})`
**Starting Condition:** `tests/test_validators.py` exists
**Expected Output:**
- Test file: `tests/test_validators.py`
- Test functions: `test_validate_email_valid`, `test_validate_email_invalid`

**Pass Condition:** Finds test file with test function names
**Fail Condition:** Returns no tests

---

### SC-MCP-007: Search Code

**Agent Input:** `search_code({"query": "password hashing"})`
**Starting Condition:** Repository contains password hashing in `app/auth/passwords.py`
**Expected Output:**
- Results include `hash_password` function
- File path and line range provided
- Confidence: EXTRACTED

**Pass Condition:** Returns password hashing related code
**Fail Condition:** Returns empty or unrelated results

---

### SC-MCP-008: Get File Context

**Agent Input:** `get_file_context({"file_path": "app/auth/login.py"})`
**Starting Condition:** File exists and is indexed
**Expected Output:**
- File summary
- List of symbols with line ranges
- Imports
- Related files

**Pass Condition:** Returns complete file structure
**Fail Condition:** Returns incomplete or wrong information

---

## 8. Anti-Duplication Scenarios

### SC-DUP-001: New File When Existing Should Be Reused

**Agent Task:** "Add email validation to registration"
**Repository Condition:** `validate_email` already exists in `app/utils/validators.py`
**Expected Behavior:** F Code suggests reusing existing function
**Expected Output:** `check_existing_implementation` returns existing match; `plan_minimal_change` recommends modifying existing file

**Pass Condition:** Agent is told to reuse existing code, not create new file
**Fail Condition:** Agent is not told about existing implementation

---

### SC-DUP-002: Duplicate Utility Function

**Agent Task:** "Create a function to format currency"
**Repository Condition:** `format_currency` already exists in `app/utils/formatters.py`
**Expected Behavior:** F Code finds existing function
**Expected Output:** `check_existing_implementation` returns match

**Pass Condition:** Existing function is found
**Fail Condition:** No match returned

---

### SC-DUP-003: Similar Function with Different Name

**Agent Task:** "Add input sanitization"
**Repository Condition:** `sanitize_input` exists in `app/utils/security.py` but named differently
**Expected Behavior:** F Code finds related function via semantic search
**Expected Output:** `search_code` returns `sanitize_input` as top result

**Pass Condition:** Semantic search finds related function
**Fail Condition:** No related results

---

## 9. Minimal Change Planning Scenarios

### SC-MIN-001: Extend Existing Endpoint

**Agent Task:** "Add rate limiting to login endpoint"
**Repository Condition:** Login endpoint exists in `app/api/auth.py`
**Expected Behavior:** Plan suggests modifying existing endpoint file
**Expected Output:** Plan modifies `app/api/auth.py`, no new files

**Pass Condition:** Plan modifies existing file
**Fail Condition:** Plan creates new file for rate limiting

---

### SC-MIN-002: Add New Module When Necessary

**Agent Task:** "Add payment processing with Stripe"
**Repository Condition:** No payment code exists
**Expected Behavior:** Plan creates new module (justified)
**Expected Output:** Plan creates `app/services/payment_service.py`

**Pass Condition:** New module created (justified because no existing code)
**Fail Condition:** Plan tries to add payment to unrelated existing file

---

## 10. Impact Analysis Scenarios

### SC-IMP-001: Change Core Function

**Agent Task:** Change `validate_email` signature
**Repository Condition:** `validate_email` is called by 3 files
**Expected Behavior:** All callers identified
**Expected Output:** List of 3 calling files, risk level: high

**Pass Condition:** All 3 callers identified
**Fail Condition:** Misses callers

---

### SC-IMP-002: Delete Unused Module

**Agent Task:** Delete `app/utils/legacy.py`
**Repository Condition:** `legacy.py` has no callers
**Expected Behavior:** Safe to delete
**Expected Output:** Risk level: low, no callers

**Pass Condition:** Correctly identifies no callers
**Fail Condition:** False positive callers

---

## 11. Deferred Retrieval Quality Scenarios

### SC-RET-001: Ambiguous Query

**Agent Input:** "How does the app handle users?"
**Expected Behavior:** Returns user-related files, symbols, routes
**Expected Output:** Multiple relevant results

**Pass Condition:** Results include user-related code
**Fail Condition:** Results are empty or unrelated

---

### SC-RET-002: Specific Symbol Query

**Agent Input:** "find function create_access_token"
**Expected Behavior:** Exact symbol match
**Expected Output:** `create_access_token` with file and lines

**Pass Condition:** Exact match found
**Fail Condition:** Symbol not found

---

### SC-RET-003: Cross-Module Query

**Agent Input:** "What connects auth to the database?"
**Expected Behavior:** Returns files that bridge auth and database
**Expected Output:** Service files, model files

**Pass Condition:** Results show auth-database connection
**Fail Condition:** Results miss the connection

---

## 12. First-Phase Indexing Test Scenarios

Every scenario below defines: fixture, command/function, expected status, expected exit code, expected SQLite rows, expected Chroma vectors, expected warnings/errors, whether previous index survives, and responsible agent.

### SC-IND-001: Valid Small Python Repository

**Fixture:** Repository with 3 Python files (app.py, utils.py, test_app.py), no secrets, no symlinks
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** repositories=1, files=3, symbols≥3, chunks≥3, code_nodes≥3, code_edges≥1, index_status=1 (status=complete)
**Expected Chroma vectors:** ≥3
**Expected warnings/errors:** 0
**Previous index survives:** N/A (first index)
**Responsible agent:** Integration Agent

---

### SC-IND-002: Empty Repository

**Fixture:** Empty directory (no files)
**Command:** `fcode index /path/to/empty_repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** repositories=1, files=0, symbols=0, chunks=0, code_nodes=0, code_edges=0, index_status=1 (status=complete, total_files=0)
**Expected Chroma vectors:** 0
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Integration Agent

---

### SC-IND-003: Repository with No Python Files (Markdown and Config Only)

**Fixture:** Repository with only README.md and config.json
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** repositories=1, files=2, symbols=0, chunks≥2 (readme_section from README.md, config from config.json), code_nodes≥2 (file nodes), code_edges=0, index_status=1 (status=complete, total_chunks≥2)
**Expected Chroma vectors:** ≥2 (readme_section chunks and config chunks are embeddable; Markdown and config files produce vectors)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Integration Agent

---

### SC-IND-004: Invalid Repository Path

**Fixture:** Non-existent path `/tmp/nonexistent_repo`
**Command:** `fcode index /tmp/nonexistent_repo`
**Expected status:** N/A (indexing never starts)
**Expected exit code:** 2
**Expected SQLite rows:** no changes
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** error code `invalid_repo_path`
**Previous index survives:** yes (no modification attempted)
**Responsible agent:** CLI/Config Agent

---

### SC-IND-005: Maximum File Count Rejection

**Fixture:** Repository with 10,001 eligible Python files
**Command:** `fcode index /path/to/repo`
**Expected status:** N/A (aborts during preflight)
**Expected exit code:** 1
**Expected SQLite rows:** no changes (preflight fails before persistent replacement)
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** error code `repository_limit_exceeded`
**Previous index survives:** yes
**Responsible agent:** Integration Agent

---

### SC-IND-006: Maximum Total Size Rejection

**Fixture:** Repository with 100 Python files totaling 51 MB
**Command:** `fcode index /path/to/repo`
**Expected status:** N/A (aborts during preflight)
**Expected exit code:** 1
**Expected SQLite rows:** no changes
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** error code `repository_limit_exceeded`
**Previous index survives:** yes
**Responsible agent:** Integration Agent

---

### SC-IND-007: Oversized Individual File

**Fixture:** Repository with one 2 MB Python file and one 1 KB Python file
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only the 1 KB file), symbols≥1, chunks≥1
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (code `file_skipped`, repo_relative_path points to the 2 MB file)
**Previous index survives:** N/A
**Responsible agent:** Integration Agent

---

### SC-IND-008: Binary File

**Fixture:** Repository with one .py file and one .png file
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only the .py file), symbols≥1
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0 (binary files are silently skipped)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-009: .env File

**Fixture:** Repository with one .env file containing `API_KEY=sk_test_123` and one app.py
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (app.py only), .env not present
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-010: Secret-Bearing File

**Fixture:** Repository with config.py containing `API_KEY=sk_test_123` and utils.py with no secrets
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=2, config.py has `has_secrets=1`, utils.py has `has_secrets=0`
**Expected Chroma vectors:** ≥1 (utils.py chunks only; config.py chunks have no vectors)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-011: Unreadable File

**Fixture:** Repository with one readable app.py and one unreadable file (permission denied)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only readable file), warning_count≥1
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (code `file_skipped`)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-012: Internal Symlink

**Fixture:** Repository with app.py and a symlink `link.py → app.py` (both inside repo)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only app.py, symlink skipped), symbols≥1
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (code `file_skipped`, repo_relative_path=`link.py`)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-013: External Symlink

**Fixture:** Repository with app.py and a symlink `ext.py → /tmp/external.py` (points outside repo)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only app.py, symlink skipped)
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (code `file_skipped`)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-014: Symlinked Directory

**Fixture:** Repository with src/app.py and a symlinked directory `linked/ → src/`
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1 (only src/app.py, linked/ directory not recursed)
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (code `file_skipped` for the directory symlink)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-015: Python Syntax Error

**Fixture:** Repository with broken.py (syntax error) and valid.py
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=2, broken.py has `parse_status='error'` and `parse_error` is non-NULL (≤500 chars), valid.py has `parse_status='parsed'`, symbols from valid.py only, warning_count≥1
**Expected Chroma vectors:** ≥1 (valid.py chunks only)
**Expected warnings/errors:** 1 warning (code `parse_warning`)
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-016: Duplicate Symbols

**Fixture:** Repository with two functions named `process` in the same file (different line ranges)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols=2 (both `process` functions stored separately with different UUIDs, different start_line/end_line)
**Expected Chroma vectors:** ≥2
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-017: Nested Function

**Fixture:** Repository with a function containing a nested closure
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥2 (outer function + nested function, each with own UUID and line range)
**Expected Chroma vectors:** ≥2
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-018: Async Function

**Fixture:** Repository with an `async def fetch_data()` function
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥1 (symbol_type=`function`, name=`fetch_data`)
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-019: FastAPI Route Without Importing FastAPI

**Fixture:** Repository with a file containing `@app.get("/users")` decorator but no FastAPI import
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥1 (route detected), code_edges≥1 (handles_route edge)
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-020: Pytest Test Extraction

**Fixture:** Repository with tests/test_utils.py containing `def test_add():` and src/utils.py containing `def add(a, b):`
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥2 (test_add + add), code_edges≥1 (tests edge from test_add → add if name matching)
**Expected Chroma vectors:** ≥2
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-021: Missing Local Embedding Model

**Fixture:** Repository with Python files; sentence-transformers model not in local cache
**Command:** `fcode index /path/to/repo`
**Expected status:** N/A (aborts during preflight)
**Expected exit code:** 1
**Expected SQLite rows:** no changes (preflight fails)
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** error code `embedding_model_unavailable`
**Previous index survives:** yes
**Responsible agent:** Integration Agent

---

### SC-IND-022: One Chunk Embedding Failure

**Fixture:** Repository with 10 Python files; one file triggers encoding failure (e.g., extremely long content)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** chunks=10, symbols≥10
**Expected Chroma vectors:** 9 (one missing due to encoding failure)
**Expected warnings/errors:** 1 warning (code `embedding_chunk_warning`), warning_count≥1
**Previous index survives:** N/A
**Responsible agent:** Chunking/Embeddings Agent

---

### SC-IND-023: All Embeddings Fail

**Fixture:** Repository with Python files; embedding model loaded but all chunks trigger encoding failure
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** index_status.status=`error`
**Expected Chroma vectors:** 0
**Expected warnings/errors:** error code `embedding_all_chunks_failed`
**Previous index survives:** yes (Phase B failure, persistent replacement not started)
**Responsible agent:** Chunking/Embeddings Agent

---

### SC-IND-024: SQLite Transaction Failure

**Fixture:** Repository with Python files; SQLite database file is read-only
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** no changes (transaction fails)
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** error code `sqlite_failure`
**Previous index survives:** yes (Phase C transaction fails, previous data intact)
**Responsible agent:** Storage Agent

---

### SC-IND-025: Chroma Failure After SQLite Commit

**Fixture:** Repository with Python files; SQLite succeeds but Chroma write fails
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** index_status.status=`error`, newly inserted data cleaned up
**Expected Chroma vectors:** 0 (cleanup deletes any partial writes)
**Expected warnings/errors:** error code `chroma_failure`
**Previous index survives:** no (Phase C has begun; previous index was deleted before Chroma write)
**Responsible agent:** Storage Agent

---

### SC-IND-026: FTS Unavailable Fallback

**Fixture:** Repository with Python files; SQLite compiled without FTS5 support
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** index_status.active_search_mode=`like_fallback`, no FTS5 virtual tables created
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 1 warning (FTS5 unavailable, LIKE fallback activated)
**Previous index survives:** N/A
**Responsible agent:** Storage Agent

---

### SC-IND-027: FTS Population Failure

**Fixture:** Repository with Python files; FTS5 available but rebuild command fails
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** index_status.status=`error`
**Expected Chroma vectors:** 0 (cleanup runs)
**Expected warnings/errors:** error code `fts_failure`
**Previous index survives:** no (Phase C has begun)
**Responsible agent:** Storage Agent

---

### SC-IND-028: Record-Count Mismatch

**Fixture:** Repository with Python files; simulated count mismatch after Phase C (e.g., FTS count ≠ chunks count)
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** index_status.status=`error`
**Expected Chroma vectors:** 0 (cleanup runs)
**Expected warnings/errors:** error code `verification_failed`
**Previous index survives:** no (Phase C has begun)
**Responsible agent:** Storage Agent

---

### SC-IND-029: Existing Index Replaced Successfully

**Fixture:** Repository already indexed with status=complete; re-run `fcode index`
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** all previous data deleted, new data inserted, index_status.status=`complete`
**Expected Chroma vectors:** new vectors match new chunks
**Expected warnings/errors:** 0
**Previous index survives:** no (replaced by new index)
**Responsible agent:** Integration Agent

---

### SC-IND-030: Failed Replacement Leaves Error State

**Fixture:** Repository already indexed; simulate Chroma failure during re-index
**Command:** `fcode index /path/to/repo`
**Expected status:** `error`
**Expected exit code:** 1
**Expected SQLite rows:** index_status.status=`error`, error_message non-NULL (≤500 chars), completed_at set
**Expected Chroma vectors:** 0 (cleaned up)
**Expected warnings/errors:** error code `chroma_failure`
**Previous index survives:** no (previous index deleted in Phase C step 3 before Chroma write)
**Responsible agent:** Integration Agent

---

### SC-IND-031: Deterministic Repeated Indexing

**Fixture:** Repository with 5 Python files; run `fcode index` twice
**Command:** `fcode index /path/to/repo` (run twice)
**Expected status:** `complete` both times
**Expected exit code:** 0 both times
**Expected SQLite rows:** second run produces identical file records, symbol records, chunk content, graph structure (UUIDs differ, ordering and content match)
**Expected Chroma vectors:** identical vectors (same model, same input)
**Expected warnings/errors:** identical warning counts
**Previous index survives:** no (replaced)
**Responsible agent:** Integration Agent

---

### SC-IND-032: Deferred CLI Commands Exit with Code 2

**Fixture:** Any indexed repository
**Command:** `fcode dashboard`, `fcode mcp --repo /path/to/repo`, `fcode setup cursor --repo /path/to/repo`
**Expected status:** N/A (no indexing)
**Expected exit code:** 2 for all three commands
**Expected SQLite rows:** no changes
**Expected Chroma vectors:** no changes
**Expected warnings/errors:** output contains "This command is not available in the first implementation slice."
**Previous index survives:** yes
**Responsible agent:** CLI/Config Agent

---

### SC-IND-033: Import Graph Metadata Reconstruction

**Fixture:** Repository with app.py importing `from utils import validate_email, format_date` at line 5, and `import os` at line 1
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** code_edges≥2 (imports edges), code_edges.metadata contains `module_name`, `imported_names`, `alias`, `line_number` for each import
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Deterministic ordering:** import edges ordered by line_number within file
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-034: Duplicate Graph Edges with Different Evidence Locations

**Fixture:** Repository with two files both importing `os` at different lines
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** code_edges≥2 (both imports edges stored separately, each with different source_file and metadata.line_number), no UNIQUE constraint violation
**Expected Chroma vectors:** ≥1
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-035: Route Symbol Persistence

**Fixture:** Repository with `@app.get("/users")` in `routes.py` with handler `list_users`
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥1 with symbol_type='route', name='GET /users', qualified_name='routes.list_users', metadata contains http_method='GET', route_path='/users', handler_function='routes.list_users'; code_nodes≥1 with node_id format `route:GET:/users:routes.py:<line_number>`; code_edges≥1 with relation='handles_route'
**Expected Chroma vectors:** ≥1 (route chunk)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-036: Variable Symbol Without Graph Node

**Fixture:** Repository with `DEBUG = True` at module level
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** symbols≥1 with symbol_type='variable', name='DEBUG'; code_nodes=0 with node_type='variable' (no variable graph nodes in first slice)
**Expected Chroma vectors:** 0 (no chunk created for bare variable assignments)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Scanner/Parser Agent

---

### SC-IND-037: Markdown/Config-Only Repository Produces Vectors

**Fixture:** Repository with README.md (# Title, ## Section) and settings.toml (50 lines)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=2, chunks≥2 (readme_section chunks for each heading, config chunk for settings.toml)
**Expected Chroma vectors:** ≥2 (readme_section and config chunks produce vectors)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Integration Agent

---

### SC-IND-038: Feature-Agent Unit-Test Ownership

**Fixture:** Repository with all feature modules
**Commands:** Verify each agent's test files exist in the correct test directory
**Expected status:** N/A (file existence check)
**Expected exit code:** N/A
**Expected test files:**
- `tests/unit/test_index_cmd.py`, `test_status_cmd.py`, `test_doctor_cmd.py`, `test_deferred_commands.py` — CLI/Config Agent
- `tests/unit/test_file_scanner.py`, `test_ignore_rules.py`, `test_secret_detector.py`, `test_python_ast.py`, `test_symbol_extractor.py`, `test_import_extractor.py`, `test_route_detector.py`, `test_graph_builder.py` — Scanner/Parser Agent
- `tests/unit/test_sqlite_store.py`, `test_chroma_store.py`, `test_graph_store.py`, `test_fts_store.py` — Storage Agent
- `tests/unit/test_chunker.py`, `test_encoder.py` — Chunking/Embeddings Agent
- `tests/golden/`, cross-module integration tests, failure-cleanup tests, scenario-matrix tests — Tests Agent
**Expected warnings/errors:** 0 missing test files
**Responsible agent:** All feature agents + Tests Agent

---

### SC-IND-039: Generic Text-Only Repository

**Fixture:** Repository with only a `.txt` file (no Python, no Markdown, no config)
**Command:** `fcode index /path/to/repo`
**Expected status:** `complete`
**Expected exit code:** 0
**Expected SQLite rows:** files=1, parse_status='not_applicable', chunks=0 (generic text files produce no chunks)
**Expected Chroma vectors:** 0 (no chunks to embed)
**Expected warnings/errors:** 0
**Previous index survives:** N/A
**Responsible agent:** Integration Agent

---

### SC-IND-040: Implementation Agent Requesting a Schema Change

**Fixture:** Any indexed repository
**Scenario:** Implementation agent discovers that `symbols.symbol_type` is missing a new type `enum` during implementation
**Required behavior:** Agent must NOT silently add the type. Agent must stop work and submit a CHANGE-REQUEST with:
- CHANGE-REQUEST ID
- Affected contract: `04_DATA_MODEL.md` — `symbols.symbol_type` CHECK constraint
- Current documented rule: `CHECK(symbol_type IN ('function', 'class', 'method', 'route', 'variable'))`
- Observed implementation problem: `enum` type definitions exist in the target repository and cannot be classified
- Proposed exact replacement: `CHECK(symbol_type IN ('function', 'class', 'method', 'route', 'variable', 'enum'))`
- Schema/API/test impact: Requires migration, symbol_extractor update, chunker update, scenario update
- Blocking status: BLOCKED
**Expected exit code:** N/A (process requirement)
**Responsible agent:** Any implementation agent

---

## 13. Privacy/Security Scenarios

### SC-PRIV-001: Secret Detection

**Repository Condition:** File contains `API_KEY=sk_test_123`
**Expected Behavior:** File flagged, content redacted
**Expected Output:** `has_secrets: true`, content shows `[REDACTED]`

**Pass Condition:** Secret redacted from chunks
**Fail Condition:** Secret appears in chunk content

---

### SC-PRIV-002: No Network Calls

**Operation:** Full indexing and retrieval cycle
**Expected Behavior:** Zero outbound network calls
**Expected Output:** All operations local

**Pass Condition:** No network traffic during operation
**Fail Condition:** Any outbound connection

---

### SC-PRIV-003: MCP Tool Refuses Write

**Agent Input:** `write_file({"path": "test.py", "content": "print('hello')"})`
**Expected Behavior:** Tool not available or refuses
**Expected Output:** Error: tool not found or not permitted

**Pass Condition:** Write operation rejected
**Fail Condition:** File written to disk

---

## 14. Performance Scenarios

### SC-PERF-001: Indexing Time

**Repository:** 1,000 Python files
**Expected Behavior:** Indexing completes within 5 minutes
**Expected Output:** Status: complete

**Pass Condition:** Indexing time < 5 minutes
**Fail Condition:** Indexing time > 10 minutes

---

### SC-PERF-002: Query Response Time

**Operation:** `search_code` with simple query
**Expected Behavior:** Response within 2 seconds
**Expected Output:** Results returned

**Pass Condition:** Response time < 2 seconds
**Fail Condition:** Response time > 5 seconds

---

### SC-PERF-003: MCP Tool Response Time

**Operation:** `check_existing_implementation`
**Expected Behavior:** Response within 3 seconds
**Expected Output:** Results returned

**Pass Condition:** Response time < 3 seconds
**Fail Condition:** Response time > 10 seconds

---

## 15. Acceptance Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| File hit rate | 90%+ | Correct files in top 5 results |
| Symbol hit rate | 85%+ | Correct symbols in results |
| Duplicate prevention rate | 80%+ | Existing code found before duplication |
| Hallucinated file count | 0 | Files referenced but not in index |
| Evidence coverage | 100% | Every answer includes evidence |
| Indexing success rate | 95%+ | Repos indexed without error |
| MCP response usefulness | 80%+ | Human-rated useful responses |
| Minimal-change plan quality | 80%+ | Plans modify existing files |

## 16. Kill/Redesign Criteria

The project must be redesigned before adding more features if:

1. **F Code cannot find existing reusable code** in golden test scenarios
2. **F Code suggests creating new files** when existing files should be reused
3. **F Code's MCP tools are too slow** (>10s per query consistently)
4. **F Code leaks repository code** to external services
5. **F Code's index is unreliable** (frequent missing/incorrect results)
6. **F Code cannot parse standard Python projects** (FastAPI, Flask, etc.)

## 17. Scenario Review Checklist

Before marking a scenario as passing:
- [ ] Scenario runs on golden test repository
- [ ] Expected output matches actual output
- [ ] Required evidence is present
- [ ] Pass condition is met
- [ ] Fail condition is not triggered
- [ ] Performance targets are met
- [ ] No secrets are exposed
- [ ] No network calls are made

## 18. Open Questions

1. **Should scenarios be automated as pytest tests?** (Locked: yes, all tests use pytest. Create `tests/golden/` with scenario tests. Unit tests in `tests/unit/`, integration tests in `tests/integration/`.)
2. **How often should golden scenarios be run?** (Recommended: on every PR, and weekly regression.)
3. **Should scenarios include multi-file change scenarios?** (Recommended: yes, but simpler ones first.)
4. **Should scenarios test error recovery (broken repos, missing files)?** (Recommended: yes, see Section 12.)
5. **Should scenarios include performance benchmarks?** (Recommended: yes, see Section 14.)
