# Security Policy

DeepOrra is a local-first repository intelligence tool. Index data stays on
your machine. The MCP server is stdio-only and read-only. The dashboard binds
to localhost only. No repository code is uploaded to any server.

## Supported Versions

Before v0.1.0, the current `main` branch is pre-release. After v0.1.0, the
latest released minor version is the supported line unless this policy is
updated.

| Version | Supported |
|---------|-----------|
| latest release | Yes |
| older releases | No |
| main (pre-release) | Best-effort — no patch commitment |

## Reporting a Vulnerability

DeepOrra uses **GitHub private vulnerability reporting** as the primary
reporting channel:

1. Navigate to the repository on GitHub.
2. Select **Security → Advisories → Report a vulnerability**.
3. Fill in the advisory form.

**Do not open a public GitHub issue containing vulnerability details.**
Public issues are for feature requests and bug reports that do not involve
security.

## What to Include

Provide as much of the following as possible:

- Affected version or commit SHA
- Steps to reproduce the issue
- Observed and expected behavior
- Impact assessment (e.g., information disclosure, denial of service)
- Environment details (OS, Python version, dependencies)
- Any possible mitigation or workaround you have identified

Maintainers may request additional information during triage.

## Coordinated Disclosure

We ask that you wait to disclose the vulnerability publicly until:

- A fix has been released in a new version, or
- A coordinated decision has been reached that no fix is required

This protects users who have not yet upgraded.

## Scope

The following security boundaries are in scope for DeepOrra:

- **Local source handling:** no repository code leaves the machine
- **Secret exclusion and redaction:** `.env` files are excluded; detected
  secrets in scanned files are redacted before storage
- **ZIP and path safety:** archives are validated for traversal, symlinks,
  and compression bombs; path inputs are resolved and normalized
- **Workspace ownership:** index data is written only into `.deeporra/`
  inside the user's repository
- **Atomic index promotion:** generation pointers are written via atomic
  rename with rollback on verification failure
- **MCP read-only enforcement:** MCP tools query index data only; no write
  SQL, no file modification, no shell execution, no network access
- **Dashboard localhost binding:** binds to `127.0.0.1` by default with
  no external access
- **Offline operation:** after model installation, indexing and querying
  run without network access

## Security Expectations and Limitations

- DeepOrra is not a security tool and does not guarantee complete detection
  of all secrets, vulnerabilities, or sensitive information in a codebase.
- Secret detection uses pattern-based heuristics and will miss
  non-standard or obfuscated secrets.
- The MCP server is read-only and planning-only by design. It must not be
  extended to perform write operations, run shell commands, or access the
  network.
- No guaranteed response or remediation timeline is made. Reports are
  handled on a best-effort basis by the maintainers.
- The dashboard is unprotected (no authentication). It should only be run
  on a machine where localhost access is trusted.
