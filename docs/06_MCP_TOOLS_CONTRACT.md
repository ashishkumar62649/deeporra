# 06_MCP_TOOLS_CONTRACT.md — F Code MCP Tools Contract

## 1. MCP Overview

F Code exposes read-only, planning-only tools to coding agents via the Model Context Protocol (MCP) stdio transport. These tools help agents find existing code, check for duplicates, understand impact, and plan minimal changes — all without writing files or executing commands.

## 2. Local Stdio Principle

The MCP server communicates via stdio (stdin/stdout). No network port. No HTTP. No external connections. The coding agent launches the MCP server as a subprocess and communicates via the MCP protocol.

## 3. Privacy Principle

No repository code is sent to external services. All tool responses are generated from local storage (SQLite + Chroma). The MCP server does not make network calls.

## 4. Tool Safety Rules

Current build MCP tools must NOT:

- Write, edit, or delete any files
- Run shell commands
- Install dependencies
- Apply patches or generate diffs
- Upload code to any server
- Access the network
- Execute user code
- Modify the `.fcode/` index

## 5. Current Build Tool List

| Tool | Purpose |
|------|---------|
| `search_code` | Semantic + keyword search for code |
| `find_symbol` | Exact symbol lookup by name |
| `get_file_context` | Get file summary and structure |
| `find_related_files` | Find files related to a target via graph |
| `check_existing_implementation` | Check if functionality already exists |
| `plan_minimal_change` | Recommend minimal changes for a task |
| `find_related_tests` | Find tests related to a function/file |
| `explain_change_impact` | Analyze what breaks if a file changes |

## 6. Tool Schemas

### 6.1 search_code

**Purpose:** Find code matching a natural language description or keywords.

**Input:**
```json
{
  "query": "email validation function",
  "file_type": "source",
  "language": "python",
  "max_results": 10
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| query | string | yes | Natural language query or keywords |
| file_type | string | no | Filter: source, test, config, doc |
| language | string | no | Filter: python, etc. |
| max_results | integer | no | Max results (default 10, max 50) |

**Output:**
```json
{
  "results": [
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
  ],
  "total_results": 1,
  "query": "email validation function"
}
```

**Retrieval methods used:** Semantic search (Chroma), keyword search (FTS5), metadata filter.

**Failure behavior:** Returns empty results with `total_results: 0`. Never raises an error.

---

### 6.2 find_symbol

**Purpose:** Find a specific symbol (function, class, method) by exact name.

**Input:**
```json
{
  "name": "validate_email",
  "symbol_type": "function"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Symbol name (exact match) |
| symbol_type | string | no | Filter: function, class, method, route |

**Output:**
```json
{
  "results": [
    {
      "id": "sym_uuid",
      "name": "validate_email",
      "qualified_name": "app.utils.validators.validate_email",
      "symbol_type": "function",
      "file_path": "app/utils/validators.py",
      "start_line": 42,
      "end_line": 68,
      "signature": "def validate_email(email: str) -> bool",
      "docstring": "Validate an email address format.",
      "calls": ["re.match", "len"],
      "called_by": ["register_user", "update_email"]
    }
  ],
  "total_results": 1
}
```

**Retrieval methods used:** Symbol lookup (SQLite), graph traversal (callers/callees).

**Failure behavior:** Returns empty results. Never raises an error.

---

### 6.3 get_file_context

**Purpose:** Get a summary and structural overview of a specific file.

**Input:**
```json
{
  "file_path": "app/utils/validators.py"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file_path | string | yes | Relative path from repo root |

**Output:**
```json
{
  "file_path": "app/utils/validators.py",
  "language": "python",
  "line_count": 120,
  "summary": "Validation utility functions for user input",
  "symbols": [
    {
      "name": "validate_email",
      "type": "function",
      "start_line": 42,
      "end_line": 68,
      "signature": "def validate_email(email: str) -> bool"
    },
    {
      "name": "validate_password",
      "type": "function",
      "start_line": 71,
      "end_line": 95,
      "signature": "def validate_password(password: str) -> bool"
    }
  ],
  "imports": [
    {"module_name": "re", "imported_names": ["match"], "alias": null, "line_number": 1},
    {"module_name": "typing", "imported_names": ["Optional"], "alias": null, "line_number": 5}
  ],
  "routes": [],
  "related_files": ["app/api/auth.py", "tests/test_validators.py"]
}
```

**Retrieval methods used:** SQLite metadata lookup, graph traversal (related files).

**Failure behavior:** Returns error object with `error: "file_not_found"` if file not indexed.

---

### 6.4 find_related_files

**Purpose:** Find files related to a target file or symbol via code relationships.

**Input:**
```json
{
  "target": "app/services/auth_service.py",
  "max_hops": 2,
  "relation_types": ["calls", "imports", "defines", "inherits", "tests", "handles_route"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| target | string | yes | File path or symbol name |
| max_hops | integer | no | Max graph hops (default 2, max 3) |
| relation_types | array | no | Filter by edge types |

**Output:**
```json
{
  "target": "app/services/auth_service.py",
  "related_files": [
    {
      "file_path": "app/api/auth.py",
      "relation": "imports",
      "confidence": "EXTRACTED",
      "hop_count": 1
    },
    {
      "file_path": "app/models/user.py",
      "relation": "calls",
      "confidence": "EXTRACTED",
      "hop_count": 1
    },
    {
      "file_path": "tests/test_auth.py",
      "relation": "tests",
      "confidence": "INFERRED",
      "hop_count": 1
    }
  ],
  "total_related": 3
}
```

**Retrieval methods used:** Graph traversal (SQL recursive CTE).

**Failure behavior:** Returns empty results if target not found in graph.

---

### 6.5 check_existing_implementation

**Purpose:** Check if requested functionality already exists in the repository. This is the core duplicate-prevention tool.

**Input:**
```json
{
  "feature": "email validation",
  "context": "We need to add email validation to the registration form"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| feature | string | yes | Description of the requested feature |
| context | string | no | Additional context about why this is needed |

**Output:**
```json
{
  "existing": true,
  "confidence": "EXTRACTED",
  "matches": [
    {
      "file_path": "app/utils/validators.py",
      "symbol_name": "validate_email",
      "symbol_type": "function",
      "start_line": 42,
      "end_line": 68,
      "signature": "def validate_email(email: str) -> bool",
      "match_reason": "Function validates email format using regex",
      "relevance_score": 0.95,
      "can_reuse": true,
      "reuse_suggestion": "Import and call validate_email() from app/utils/validators.py"
    }
  ],
  "recommendation": "Existing implementation found. Reuse validate_email() instead of creating new code.",
  "evidence": {
    "semantic_matches": 3,
    "keyword_matches": 5,
    "graph_connections": 2
  }
}
```

**Retrieval methods used:** Semantic search, keyword search, symbol lookup, graph analysis.

**Algorithm:**
1. **Retrieve candidates:**
   - Semantic: encode `feature` query → Chroma search → top 10 chunks
   - Keyword: FTS5 match on `feature` terms → top 10 chunks
   - Symbol: exact match on `feature` as symbol name → direct hit if found
2. **Deduplicate:** Merge results by (file_path, symbol_name), keep highest score
3. **Score candidates:** Apply hybrid ranking formula (see `05_INDEXING_AND_RETRIEVAL.md` Section 18)
4. **Filter:** Keep only candidates with score >= 0.35 (weak match threshold)
5. **Decide `existing`:**
   - If any candidate has score >= 0.55 (strong match) → `existing = true`
   - If best candidate has score 0.35-0.54 → `existing = true` with `confidence: "AMBIGUOUS"`
   - If no candidate >= 0.35 → `existing = false`
6. **Build matches:** For each candidate >= 0.35, include:
   - `file_path`, `symbol_name`, `symbol_type`, `start_line`, `end_line`, `signature`
   - `match_reason`: first applicable from: exact qualified-name match, exact symbol-name match in a relevant file, strong semantic and keyword agreement, strong semantic similarity, strong keyword match, graph-supported related implementation, weak candidate requiring review
   - `relevance_score`: the computed score
   - `can_reuse`: `true` if function is importable (not a route handler or test)
   - `reuse_suggestion`: specific import path if `can_reuse` is true
7. **Build recommendation:**
   - If `existing = true` and best match `can_reuse = true`: "Existing implementation found. Reuse {symbol_name} instead of creating new code."
   - If `existing = true` and best match `can_reuse = false`: "Existing implementation found but not directly reusable. Consider adapting {symbol_name}."
   - If `existing = false`: "No existing implementation found. New code may be needed."
8. **Evidence summary:** Count semantic_matches, keyword_matches, graph_connections from retrieval

**Failure behavior:** Returns `existing: false` if no match found. Never raises an error.

---

### 6.6 plan_minimal_change

**Purpose:** Recommend the smallest set of changes to existing files for a given task.

**Input:**
```json
{
  "task": "Add email validation to user registration",
  "target_files": ["app/api/auth.py"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task | string | yes | Description of the desired change |
| target_files | array | no | Files to focus on (if known) |

**Output:**
```json
{
  "task": "Add email validation to user registration",
  "plan": {
    "approach": "Modify existing files",
    "changes": [
      {
        "file_path": "app/api/auth.py",
        "action": "modify",
        "description": "Import validate_email and add validation call in register endpoint",
        "lines_affected": [12, 45],
        "reason": "Registration endpoint already exists at line 45"
      }
    ],
    "new_files": [],
    "dependencies_to_add": [],
    "tests_to_update": ["tests/test_auth.py"],
    "risk_level": "low",
    "confidence": "EXTRACTED"
  },
  "existing_code_to_reuse": [
    {
      "file_path": "app/utils/validators.py",
      "symbol_name": "validate_email",
      "reason": "Already implements email validation"
    }
  ],
  "minimal_change_principle": "Modify the existing registration endpoint to call the existing validate_email function. No new files needed."
}
```

**Retrieval methods used:** Semantic search, graph traversal, symbol lookup.

**Algorithm:**
1. **Gather context:**
   - Semantic: encode `task` query → Chroma search → top 5 chunks
   - If `target_files` provided: get file context for each (symbols, imports, structure)
   - If not provided: identify likely target files from semantic results
2. **Find existing code to reuse:**
   - For each candidate from semantic search: check if it already implements part of the task
   - Use `check_existing_implementation` logic for each candidate
   - Collect all reusable symbols
3. **Identify change points:**
   - For each target file: find the minimal insertion/modification points
   - Prefer: adding imports + calling existing functions over rewriting logic
   - Prefer: modifying existing functions over creating new ones
   - Prefer: small edits (1-10 lines) over large rewrites
4. **Build changes list:**
   - For each file that needs modification:
     - `file_path`: the file to change
     - `action`: "modify" (preferred), "extend" (add to existing function), or "create" (last resort)
     - `description`: specific change description (e.g., "Import validate_email and add call in register endpoint")
     - `lines_affected`: estimated line numbers
     - `reason`: why this change is minimal
5. **New files (last resort):**
   - Only if no existing file can be extended
   - `new_files` list: file path, reason why existing files cannot be extended
   - Must justify why modification of existing code is insufficient
6. **Dependencies:**
   - List any new package imports needed (should be rare)
   - Flag if new dependencies are required (escalate to user)
7. **Test updates:**
   - Find related tests via `find_related_tests` logic
   - List tests that need updating
8. **Risk assessment:** See risk level calculation below
9. **Confidence:**
   - "EXTRACTED" if all changes are based on exact code matches
   - "INFERRED" if some changes are based on patterns or heuristics
   - "AMBIGUOUS" if insufficient information to plan confidently

**New file restrictions:**
- New files require explicit justification in the plan
- Must explain why existing files cannot be modified
- Must show that the new file has no equivalent in existing codebase

**Minimal change rules:**
1. Reuse existing functions/classes before writing new ones
2. Modify existing files before creating new ones
3. Add imports before duplicating logic
4. Prefer extending existing functions over creating wrappers
5. Never create abstractions with one implementation

**Failure behavior:** Returns plan with `confidence: "AMBIGUOUS"` if insufficient information.

---

### 6.7 find_related_tests

**Purpose:** Find test files and test functions related to a given function or file.

**Input:**
```json
{
  "target": "app/utils/validators.py"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| target | string | yes | File path or function name |

**Output:**
```json
{
  "target": "app/utils/validators.py",
  "related_tests": [
    {
      "file_path": "tests/test_validators.py",
      "test_functions": [
        {"name": "test_validate_email_valid", "line": 12},
        {"name": "test_validate_email_invalid", "line": 18},
        {"name": "test_validate_password_strength", "line": 25}
      ],
      "relation": "tests",
      "confidence": "EXTRACTED"
    }
  ],
  "total_test_files": 1,
  "total_test_functions": 3
}
```

**Retrieval methods used:** Graph traversal (tests edges), file path convention matching.

**Failure behavior:** Returns empty results if no tests found.

---

### 6.8 explain_change_impact

**Purpose:** Analyze what will break if a specific function, class, or file is changed.

**Input:**
```json
{
  "target": "app/utils/validators.py",
  "change_type": "modify_function",
  "function_name": "validate_email"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| target | string | yes | File path |
| change_type | string | no | modify_function, delete_file, change_signature |
| function_name | string | no | Specific function to analyze |

**Output:**
```json
{
  "target": "app/utils/validators.py",
  "change_type": "modify_function",
  "function_name": "validate_email",
  "impact": {
    "direct_callers": [
      {"file": "app/api/auth.py", "function": "register_user", "line": 45},
      {"file": "app/api/users.py", "function": "update_email", "line": 23}
    ],
    "indirect_callers": [
      {"file": "app/services/user_service.py", "function": "create_user", "line": 67}
    ],
    "affected_tests": [
      {"file": "tests/test_validators.py", "function": "test_validate_email_valid"},
      {"file": "tests/test_auth.py", "function": "test_register_with_email"}
    ],
    "risk_level": "medium",
    "risk_reason": "2 direct callers, 1 indirect caller, 2 tests affected",
    "safe_change_strategy": "Ensure backward compatibility of validate_email signature. Update callers only if return type changes."
  }
}
```

**Retrieval methods used:** Graph traversal (callers, callees, tests edges).

**Failure behavior:** Returns `impact: null` if target not found in graph.

---

## 6a. MCP Error Mapping

Map indexing state to MCP errors:

| Error Code | When Used |
|------------|-----------|
| `invalid_input` | Invalid tool input or invalid path argument |
| `not_found` | Valid request produced no matching entity |
| `index_not_ready` | No complete index is available |
| `index_error` | The active index status is `error` or required index storage cannot be read |
| `internal_error` | Unexpected unclassified failure |

CLI/indexing errors remain detailed internally. MCP exposes the coarse MCP envelope and may include the sanitized internal code in `error.details.internal_code`.

## 6b. `find_related_files` relation filter

Use only current relations: `defines`, `imports`, `inherits`, `calls`, `tests`, `handles_route`. Do not include `uses` unless added globally to graph contracts, SQLite CHECK constraints, graph extraction, and scenarios. `uses` is not added in this repair.

## 7. Risk Level Calculation

Risk level is used in `plan_minimal_change` and `explain_change_impact` outputs.

**Risk inputs:**
- Number of direct callers of the target function/class
- Number of indirect callers (callers of callers, up to 2 hops)
- Number of affected tests
- Whether the change modifies a function signature
- Whether the change modifies a public API

**Risk level rules:**

```
low:
- 0-2 direct callers (inclusive)
- no API route affected
- no database/model change
- related tests exist
- confidence is EXTRACTED

medium:
- 3-5 direct callers (inclusive), or
- 1 API route affected, or
- no related tests found, or
- confidence is INFERRED

high:
- 6+ direct callers, or
- database/model changes, or
- auth/security/payment code affected, or
- multiple API routes affected, or
- confidence is AMBIGUOUS
```

**Boundary notes:**
- "0-2 direct callers inclusive" means 0, 1, or 2 callers = low risk.
- "3-5 direct callers inclusive" means 3, 4, or 5 callers = medium risk.
- "6+ direct callers" means 6 or more callers = high risk.

**Highest-risk-wins:** If any single input triggers a higher risk level, use that level (e.g., 1 direct caller but public API signature change → high).

**Unknown risk:** Defaults to `medium` if graph data is insufficient or risk cannot be determined.

**Risk output:** Must include `risk_reason` field explaining why this risk level was assigned. Missing graph data must be reported in the uncertainty field.

### Deterministic `risk_reason`

Build `risk_reason` from triggered conditions in this order:
1. public API or route exposure
2. direct callers
3. dependent files
4. related tests
5. signature-change requirement
6. ambiguous evidence

Join active clauses with `"; "`. Do not use generative free-form text.

Example: `"1 API route affected; 3 direct callers; 2 dependent files; 1 related test; signature change required"`

### Deterministic `safe_change_strategy`

Use these fixed templates:

**Low risk:**
```
Modify the existing symbol directly and run its related tests.
```

**Medium risk:**
```
Modify the existing symbol while preserving its public signature where possible, then run direct and dependent tests.
```

**High risk:**
```
Make the smallest backward-compatible change, update every identified caller, route, and related test, and verify each affected path before removing old behavior.
```

**Core modules (always high risk if changed):**
- `fcode/storage/sqlite_store.py`
- `fcode/storage/chroma_store.py`
- `fcode/retrieval/hybrid_ranker.py`
- `fcode/graph/graph_builder.py`

## 8. Reason Text Generation Rules

### `match_reason`

Use the first applicable reason from this ordered list:

1. exact qualified-name match
2. exact symbol-name match in a relevant file
3. strong semantic and keyword agreement
4. strong semantic similarity
5. strong keyword match
6. graph-supported related implementation
7. weak candidate requiring review

Include evidence paths separately rather than generating prose containing paths.

Rules:
- Do not invent behavior not supported by evidence.
- Keep reason text under 160 characters.

### `evidence_reason`

Generated from retrieval signals. Examples:
- `"Exact symbol match"`
- `"Semantic match with related keywords"`
- `"Same file as top candidate"`
- `"Direct graph relationship"`
- `"Related test file by naming convention"`

Rules:
- Must be based on actual retrieval signals.
- Must include at least one signal type.
- Must not use LLM-generated unsupported explanations.

### `reuse_suggestion`

Generated from recommendation type:
- `reuse_existing_code`: `"Reuse this existing symbol instead of creating a duplicate."`
- `modify_existing_code`: `"Extend this existing file or symbol instead of creating a new one."`
- `create_new_code`: `"No reusable implementation was found; creating new code may be justified."`
- `needs_human_review`: `"Potential matches are ambiguous; review before implementing."`

## 9. Tool Output Format

All tool outputs follow this structure:

```json
{
  "tool": "tool_name",
  "success": true,
  "data": { ... },
  "error": null,
  "evidence_count": 5,
  "latency_ms": 45
}
```

Error format:
```json
{
  "tool": "tool_name",
  "success": false,
  "data": null,
  "error": {
    "code": "not_found",
    "message": "Symbol 'xyz' not found in index"
  },
  "evidence_count": 0,
  "latency_ms": 12
}
```

## 10. Error Format

| Error Code | Meaning |
|------------|---------|
| `not_found` | Requested item not in index |
| `invalid_input` | Invalid parameters |
| `index_not_ready` | Repository not yet indexed |
| `index_error` | Error during indexing |
| `internal_error` | Unexpected error |

## 11. Evidence Format

Every tool response that returns code references must include evidence:

```json
{
  "evidence": [
    {
      "file_path": "app/utils/validators.py",
      "symbol_name": "validate_email",
      "start_line": 42,
      "end_line": 68,
      "confidence": "EXTRACTED",
      "relevance_score": 0.92,
      "retrieval_method": "semantic",
      "evidence_reason": "Function validates email format"
    }
  ]
}
```

## 12. Read-Only Restrictions

The MCP server enforces read-only behavior:

1. Tool handlers only call `SELECT` queries on SQLite
2. Tool handlers only call `query()` on Chroma (no `add()`, `update()`, `delete()`)
3. No file system writes
4. No subprocess execution
5. No network calls
6. Logging writes to `tool_call_logs` table only

## 13. Agent Usage Patterns

**Before writing code:**
1. Call `check_existing_implementation` with the planned feature
2. If existing implementation found, call `find_symbol` for details
3. Call `plan_minimal_change` for the approach
4. Call `find_related_tests` to understand test coverage

**When modifying code:**
1. Call `explain_change_impact` on the target file
2. Call `find_related_files` to understand dependencies
3. Call `get_file_context` for file structure

**When debugging:**
1. Call `search_code` with error message or stack trace keywords
2. Call `find_symbol` for functions mentioned in errors
3. Call `explain_change_impact` to understand blast radius

## 14. Setup Flow

**General setup:**
1. Install F Code: `pip install fcode`
2. Index repository: `fcode index /path/to/repo`
3. Start MCP server: `fcode mcp --repo /path/to/repo`
4. Configure coding agent to use the MCP server

## 15. Claude Code Setup

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "fcode": {
      "command": "fcode",
      "args": ["mcp", "--repo", "/path/to/repo"]
    }
  }
}
```

## 16. Codex Setup

Add to `.codex/config.toml`:
```toml
[mcp_servers.fcode]
command = "fcode"
args = ["mcp", "--repo", "/path/to/repo"]
```

## 17. Gemini CLI Setup

Add to MCP config:
```json
{
  "mcpServers": {
    "fcode": {
      "command": "fcode",
      "args": ["mcp", "--repo", "/path/to/repo"]
    }
  }
}
```

## 18. OpenCode Setup

Add to `opencode.json`:
```json
{
  "mcp": {
    "fcode": {
      "command": "fcode",
      "args": ["mcp", "--repo", "/path/to/repo"]
    }
  }
}
```

## 19. Permission and Trust Model

- MCP server runs locally with user's permissions
- No elevation or special permissions required
- Read-only tools cannot modify system state
- User controls which coding agent has access to the MCP server
- No authentication required (local stdio)

## 20. Tool Logging

Every tool call is logged to `tool_call_logs` table:
- tool_name
- input_params (JSON)
- output_summary (brief)
- result_count
- latency_ms
- timestamp

Logs are visible in the dashboard (Agent Tools Preview page).

## 21. Out-of-Scope Tools

The following tools are NOT in the current build:
- `write_file` — no file writes
- `edit_file` — no file edits
- `apply_patch` — no patch application
- `run_tests` — no test execution
- `run_shell` — no shell execution
- `search_github` — no network calls
- `clone_repo` — done by CLI, not MCP

## 22. Locked MCP Decisions

1. **Multiple repositories:** One repo per server instance in current build.
2. **Full content vs previews:** Previews only; full content via `get_file_context` when needed.
3. **Rate limiting:** No rate limiting for local use.
4. **Confidence threshold:** Return all matches above 0.5 relevance score.
5. **Streaming:** No streaming in current build; synchronous responses.
