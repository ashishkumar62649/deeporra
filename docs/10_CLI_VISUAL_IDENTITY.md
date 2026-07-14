# 10_CLI_VISUAL_IDENTITY.md — DeepOrra CLI Visual Identity Specification

> **Status:** Draft — ready for human review.
> **Branch:** `docs-cli-visual-identity`
> **Baseline:** `3cd1fc5476c869218f8194e19992eb1a098c444b`

---

## 1. Audit: Current CLI Output Surfaces

Inspected by running each command against the repository at HEAD `3cd1fc5`.

### 1.1 Human-Facing Outputs (future branding candidates)

| Command | Output | Uses Rich/Typer markup? | Exit codes |
|---------|--------|--------------------------|------------|
| `deeporra` (no args) | Typer-generated help panel — box-drawing chars, `Usage:`, `Options`, `Commands` sections. Title: `DeepOrra — local-first repository intelligence tool for AI coding agents.` | Yes — Typer/Rich renders boxed layout | 0 |
| `deeporra --help` | Identical to no-args | Yes | 0 |
| `deeporra doctor <path>` | `[PASS]`/`[FAIL]` prefix per check, colon-separated name: message. No Rich styling beyond `typer.echo`. | No (`typer.echo` plain text) | 0 if all pass, 1 if any fail |
| `deeporra status <path>` | `No active index.` when empty. Otherwise `state=.. phase=..` key=value flat string. | No | 0 (healthy empty), 1 (error) |
| `deeporra index <path>` | `Index failed.` on error, `Index complete.` on success, then `scanned=N parsed=N ...` key=value. | No | 0 on success, 1 on failure |
| `deeporra dashboard` | Stub: `"This command is not available in the first implementation slice."` | No | 2 (deferred) |
| `deeporra mcp --repo <path>` | Stub: same message as dashboard. | No | 2 (deferred) |
| `deeporra setup <agent> --repo <path>` | Stub: same message, or `Invalid agent ...` for bad agent name. | No | 2 (deferred), 1 (bad args) |
| Error fallthrough (unhandled exception) | `typer.echo("Index failed.")` or generic Python traceback to stderr. | No | 1 |

### 1.2 Machine-Safe Outputs (must stay machine-safe)

| Surface | Format | Must NOT change |
|---------|--------|----------------|
| MCP stdio: `python -m deeporra.mcp_server` | Pure JSON-RPC 2.0 over stdin/stdout. No human-readable banner. No ANSI. No box-drawing. | Any human decoration. No banner. No ANSI. |
| MCP tool responses | `json.dumps(...)` of serialised dicts | JSON structure. No extra text. |
| `typer.echo` when stdout is piped | Same plain text as interactive — no Rich rendering applied by Typer when stdout is not a TTY | No ANSI codes, no box-drawing. Future banner should detect pipe and suppress. |
| `subprocess` callers (tests) | Tests parse stdout for exact strings: `"Index failed."`, `"No active index."`, `"Index complete."`, `"This command is not available..."` | Any change to these exact strings breaks test assertions. |

### 1.3 Key Observations

- `deeporra --help` already uses Rich box-drawing via Typer (the boxed table format). This is Typer's default theme, not custom DeepOrra branding.
- All functional command output (`doctor`, `status`, `index`) is plain text with no ANSI codes, no colour, no Rich console markup. The term branding is a *de novo* addition.
- No command currently displays a banner, logo, or wordmark.
- The Typer app `no_args_is_help=True` means `deeporra` with no arguments shows the help panel.
- The MCP server entry point (`deeporra/mcp_server/__main__.py`) runs `asyncio.run(server.run_stdio_async())` — it never calls `typer.echo` or prints to stdout except for JSON-RPC protocol messages. It must remain banner-free.
- Current tests assert exact string matches for human-facing messages (e.g., `"No active index."`, `"Index complete."`). Adding visual decoration must not break these assertions — either decorate through new channels or update tests in lockstep.

---

## 2. Brand Token Palette

### 2.1 Semantic Roles

| Role | Colour (RGB hex) | ANSI code | Description |
|------|------------------|-----------|-------------|
| **Primary background** | `#0D1117` | — | Deep dark background (GitHub-dark inspired, near-black). Used for the wordmark banner background. |
| **Accent cyan** | `#00E5FF` | `96` (bright cyan) | Electric cyan. Primary accent for the DeepOrra name, active indicators, progress highlights. |
| **Accent indigo** | `#7C3AED` | — | Deep violet/indigo. Secondary accent for graph-node constellation, secondary decorative elements. |
| **Accent violet** | `#A78BFA` | `95` (bright magenta) | Lighter violet for secondary highlights, subtle decorations. |
| **Text primary** | `#E6EDF3` | `97` (bright white) | High-contrast off-white for body text and command descriptions. |
| **Text muted** | `#8B949E` | `90` (dark grey) | Secondary text, metadata, file paths, timing info. |
| **Success** | `#3FB950` | `92` (green) | PASS status, completion messages. |
| **Warning** | `#D29922` | `93` (yellow) | WARNING severity, non-fatal diagnostics. |
| **Error** | `#F85149` | `91` (red) | FAIL status, fatal errors. |
| **Info** | `#58A6FF` | `94` (blue) | Informational messages, hints. |

### 2.2 Monochrome Fallback

When colour is unavailable (NO_COLOR, piped, accessibility):

| Role | Monochrome marker |
|------|-------------------|
| Success | `[PASS]` or `✔` |
| Warning | `[WARN]` or `⚠` |
| Error | `[FAIL]` or `✖` |
| Info | `[INFO]` or `•` |
| DeepOrra name | Plain `DeepOrra` |

### 2.3 Unicode and ASCII Fallback Characters

| Purpose | Unicode (preferred) | ASCII fallback |
|---------|---------------------|----------------|
| Bullet / info marker | `•` (U+2022) | `*` |
| Checkmark / pass | `✔` (U+2714) | `[PASS]` |
| Cross / fail | `✖` (U+2716) | `[FAIL]` |
| Warning | `⚠` (U+26A0) | `[WARN]` |
| Arrow / progress | `→` (U+2192) | `->` |
| Telescope symbol | `🔭` (U+1F52D) | `[D]` (for DeepOrra) |
| Graph-node dot | `●` (U+25CF) | `o` |
| Separator line | `─` (U+2500) | `-` |
| Corner (compact logo) | `◆` (U+25C6) | `*` |

The ASCII fallback must be used when:
- `FORCE_ASCII=1` environment variable is set
- Terminal encoding is not UTF-8 (checked via `sys.stdout.encoding`)
- Output is piped or redirected

---

## 3. Terminal Logo Modes

### 3.1 Full Interactive Wordmark

**Intended width:** ~60–80 characters (wide terminals ≥80 columns)

**Mockup:**

```
╭──────────────────────────────────────────────────────────────╮
│   ◆◆◆ ◆◆◆                                                 │
│     ◆ ◆    ██████  ███████ ███████ ██████   █████  ██████   │
│     ◆ ◆    ██   ██ ██      ██      ██   ██ ██   ██ ██   ██  │
│     ◆ ◆    ██   ██ █████   █████   ██████  ███████ ██████   │
│     ◆ ◆    ██   ██ ██      ██      ██   ██ ██   ██ ██      │
│   ◆◆◆ ◆◆◆  ██████  ███████ ██      ██   ██ ██   ██ ██      │
│   ───────────────────────────────────────────────────────   │
│   local-first repository intelligence for AI coding agents  │
╰──────────────────────────────────────────────────────────────╯
```

**Usage:** Shown once at the top of interactive human-facing commands:
- `deeporra` (no args, before help panel)
- `deeporra --help` (before help panel)
- `deeporra index <path>` (before progress)
- `deeporra status <path>` (before status output)
- `deeporra doctor <path>` (before diagnostics)

**Design notes:**

- The diamond `◆` cluster (4 small diamonds in a 2×2 grid) represents the **graph-node constellation** — the four dots evoke connected code nodes.
- The large block-letter `DEEPORRA` uses a consistent 6-row block-letter ASCII art. The `D` shape references the observatory/telescope dome silhouette.
- The separator line and tagline make it recognisable without needing colour.
- The border uses box-drawing characters (`╭─╮│╰─╯`). Falls back to `+-+ | +-+` when ASCII fallback required.

### 3.2 Compact Symbol Wordmark

**Intended width:** ~24–40 characters (medium/narrow terminals ≥40 columns)

**Mockup:**

```
◆◆◆ ◆◆◆  DeepOrra
```

**Usage:** For terminals with width <80 columns but ≥40 columns, or when the full wordmark feels too heavy (e.g., status output refresh).

**Design notes:**

- Same diamond constellation `◆◆◆ ◆◆◆` from the full wordmark.
- Tooltip name `DeepOrra` in compact form.
- When colour is available: diamonds in cyan (`\033[96m`) and violet (`\033[95m`), name in bold bright white.
- The diamond constellation is the persistent visual signature — always present, always recognisable.

### 3.3 Plain-Text Fallback

**Text:** `DeepOrra`

**Usage:**
- When `NO_COLOR` is set and output is interactive but narrow
- When `FORCE_ASCII=1` is set
- When `sys.stdout.encoding` is not UTF-8
- When output is piped or redirected
- **Always** in MCP stdio context (never show any banner)

**Design notes:**
- No glyphs, no box-drawing, no ANSI codes.
- The italics/emph is conveyed by the name itself — it's short and recognisable.
- Accessibility-first: screen readers read `DeepOrra` without interference.
- Automation-safe: no special characters to confuse parsers.

---

## 4. Rendering and Safety Rules

### 4.1 Interactive Detection

- A human-facing entry point is defined as: the command is invoked directly by a user in a terminal (not piped, not a subprocess, not MCP).
- Detection logic (pseudocode):
  ```python
  def is_interactive() -> bool:
      if "NO_COLOR" in os.environ:
          return False
      if not sys.stdout.isatty():
          return False
      return True
  ```
- A future `--no-color` flag must override detection and force plain mode.

### 4.2 Terminal Width Detection

- Detect via `shutil.get_terminal_size((80, 20)).columns` (stdlib, no dependencies).
- Thresholds:
  - ≥80 columns → full wordmark
  - 40–79 columns → compact wordmark
  - <40 columns → plain fallback

### 4.3 NO_COLOR Handling

- If `NO_COLOR` environment variable is set (to any value, including empty):
  - Suppress all ANSI colour sequences.
  - Suppress all box-drawing/border characters.
  - Use monochrome fallback markers (`[PASS]`/`[FAIL]`/`[WARN]`).
  - Use plain-text `DeepOrra` (no banner).
- Standard: [no-color.org](https://no-color.org/).
- This applies globally, not only to banners.

### 4.4 Redirected / Piped Output

- If stdout is not a TTY (`not sys.stdout.isatty()`):
  - No banner, no wordmark, no compact logo.
  - No ANSI codes.
  - No box-drawing characters.
  - Keep current key=value output format (machine-parseable).
- The `doctor` `[PASS]`/`[FAIL]` format is already machine-readable — preserve it as-is.

### 4.5 Structured (JSON) Output

- No banner in JSON output mode (future `--json` flag, not yet implemented).
- JSON output must contain only the requested data, serialised.
- Visual decoration is never emitted in JSON mode.

### 4.6 MCP stdio Protection

- **No banner, no logo, no echo, no decoration** in the MCP process.
- MCP communicates exclusively through JSON-RPC 2.0 over stdin/stdout.
- Any stray stdout text would break the JSON-RPC protocol and crash the MCP connection.
- The MCP entry point (`deeporra/mcp_server/__main__.py`) must never import or call any banner-rendering code.
- Future `deeporra mcp` (the CLI stub) transitions to real: the CLI stub's banner is discarded — the actual MCP server process must have zero decoration.

### 4.7 Terminal Clearing

- **Never** clear the terminal screen.
- **Never** use `\033c`, `\033[2J`, or any cursor-positioning escape that erases scrollback.
- Banner output appears in-band, after any prior terminal content.

### 4.8 Screen-Reader / Accessibility

- All visual decoration must degrade gracefully:
  - ASCII fallback for all Unicode markers.
  - No colour-only information — always pair colour with text labels (`✔` + `[PASS]` or just `[PASS]`).
  - Banner is a single logical line for screen readers (no large empty regions).
  - The compact logo `◆◆◆ ◆◆◆ DeepOrra` reads as "DeepOrra" — the diamonds are decorative.
  - The full wordmark's tagline reads as a distinct sentence.
- Avoid over-decoration: one banner per command invocation, not repeated on every status line.

### 4.9 Error Message Conciseness

- Error output must remain short and actionable.
- No wrapping errors in box-drawing borders.
- Error prefix indicators:
  - With colour: `\033[91merror:\033[0m` (red "error:")
  - With monochrome: `error:`
  - Example: `error: embedding_model_unavailable: Local embedding model is unavailable.`
- Keep the current `error: {code}: {message}` format for index errors.

---

## 5. Future Implementation Plan

### 5.1 Proposed Files to Create or Modify

| File | Change | Priority |
|------|--------|----------|
| `deeporra/cli/brand.py` | **New.** Helper module: banner rendering, terminal detection, colour helper, logo selection (full/compact/plain). Single-file, no abstractions. | Batch 1 |
| `deeporra/cli/main.py` | Import and call brand helper before the Typer app runs. Show banner only for interactive top-level entry. | Batch 1 |
| `deeporra/cli/commands/doctor_cmd.py` | Apply `_print_result` formatting: colour-coded `[PASS]`/`[FAIL]` via brand helper. | Batch 2 |
| `deeporra/cli/commands/index_cmd.py` | Apply colour to `Index complete.` / `Index failed.` messages. | Batch 2 |
| `deeporra/cli/commands/status_cmd.py` | Apply colour to `No active index.` / status labels. | Batch 2 |
| `deeporra/utils/health.py` | No change needed. Doctor logic is output-format agnostic. | — |

### 5.2 Helper Boundaries

`deeporra/cli/brand.py` exposes:

```python
def get_terminal_mode() -> str: ...
    # Returns "full", "compact", "plain"

def render_banner(mode: str) -> str: ...
    # Returns the appropriate banner string (or "" for plain)

def colorize(text: str, role: str, force_ascii: bool = False) -> str: ...
    # Wraps text in ANSI codes for the given semantic role

def status_marker(passed: bool) -> str: ...
    # Returns "✔" or "[PASS]" (monochrome) / colour equivalent
```

- `brand.py` must not import from CLI commands, indexing, storage, or any feature module.
- It may import from `os`, `sys`, `shutil`, and `deeporra/__init__.py` (version string only).
- It must not depend on `rich`, `typer`, or any non-stdlib package except for the DeepOrra version constant.

### 5.3 Tests Required

| Test file | Scope |
|-----------|-------|
| `tests/unit/test_cli_brand.py` | Terminal mode detection (mock isatty, COLUMNS, NO_COLOR). |
| `tests/unit/test_cli_brand.py` | Banner output matches expected mockup for each mode. |
| `tests/unit/test_cli_brand.py` | No ANSI codes in plain mode or when NO_COLOR set. |
| `tests/unit/test_cli_brand.py` | ASCII fallback when encoding not UTF-8. |
| `tests/unit/test_cli_brand.py` | Colorize returns empty string for unknown role. |
| `tests/acceptance/` | Golden test: subprocess capture of `deeporra --help` shows banner when interactive, does not show when piped. |
| `tests/acceptance/` | Golden test: `deeporra doctor` output with/without NO_COLOR. |
| `tests/acceptance/` | MCP subprocess: verify no stray text on stdout. |

### 5.4 Platform Checks

| Platform | Check | Action |
|----------|-------|--------|
| Windows Terminal / PowerShell | `$Host.UI.RawUI.WindowSize.Width` or `shutil.get_terminal_size()` works correctly. | Test width detection on Windows with various console widths. |
| Windows PowerShell 5.1 | Unicode output with UTF-8 codepage. | Detect `[Console]::OutputEncoding` equivalent via `sys.stdout.encoding`. Fall back to ASCII if not UTF-8. |
| Linux shell | `$COLUMNS` environment variable. | `shutil.get_terminal_size` handles this. |
| macOS Terminal | Same as Linux. | — |
| CI / headless | No TTY → plain mode. | Verified by `isatty()` returning False. |

### 5.5 Snapshot / Golden-Output Risks

- **Snapshot tests** for CLI output are fragile because:
  - Terminal width changes between environments.
  - Typer/Rich box-drawing may vary between Rich versions.
  - Colour codes differ between terminal emulators (true colour vs 256-colour).
- **Mitigation:**
  - Do NOT write snapshot tests for the full `--help` output (too many variables).
  - Write targeted tests for `brand.py` functions (unit tests, deterministic input/output).
  - Acceptance tests for subprocess should check for expected *substrings* (e.g., `"DeepOrra"` present, `"\033[91m"` absent under NO_COLOR) rather than full golden output.

### 5.6 MCP Regression Protections

- Add a CI test that runs `python -m deeporra.mcp_server` with a known input and verifies no stray text before the first JSON-RPC response.
- Protect against accidental import of `brand.py` from MCP code: add a lint rule or module-level guard.
- If `brand.py` is ever accidentally imported in the MCP process, it must not print anything at import time.

### 5.7 Implementation Batches

**Batch 1 — Foundation (files: 2 new, 1 modified)**
1. Create `deeporra/cli/brand.py` with terminal detection, banner rendering, colour helpers.
2. Modify `deeporra/cli/main.py` to show banner before app help.
3. Add `tests/unit/test_cli_brand.py` for unit tests.
4. Verify: `deeporra --help` shows banner interactively, no banner when piped.

**Batch 2 — Command decoration (files: 3 modified)**
1. Update `doctor_cmd.py` `_print_result` to use `colorize` and `status_marker`.
2. Update `index_cmd.py` to colour success/error messages.
3. Update `status_cmd.py` to colour status labels.
4. Update existing subprocess tests to handle coloured output or assert substring presence.

**Batch 3 — MCP safety and CI (files: 1 test)**
1. Add MCP no-banner regression test.
2. Add NO_COLOR / piped-output acceptance test.
3. Add Windows-specific width-detection test (if practical in CI).

---

## 6. Output Surface Classification

### Human-Facing (banner eligible, colour eligible)

- `deeporra` / `deeporra --help` (before help panel)
- `deeporra index <path>` output lines
- `deeporra status <path>` output lines
- `deeporra doctor <path>` output lines
- `deeporra dashboard` (stub)
- `deeporra mcp --repo <path>` (stub — the *CLI stub* shows banner, but the *real* MCP process must not)
- `deeporra setup <agent>` error messages

### Machine-Safe (no banner, no colour, no decoration)

- `python -m deeporra.mcp_server` (any output on stdout)
- `python -m deeporra status --json` (future)
- Piped/redirected stdout: `deeporra index . | cat`
- Subprocess callers (tests, CI scripts, editor integrations)
- `typer.echo` output with `NO_COLOR`
- Structured output (future `--json` flag on any command)

---

## 7. Scope

- **Document created:** `docs/10_CLI_VISUAL_IDENTITY.md`
- **Source changes:** None
- **Test changes:** None
- **Dependency changes:** None
- **Commit:** Not performed
- **Push:** Not performed
- **Final Git status:** See below

### Final Git Status (worktree)

```
On branch docs-cli-visual-identity
Changes not staged for commit:
  new file:   docs/10_CLI_VISUAL_IDENTITY.md
```

---
