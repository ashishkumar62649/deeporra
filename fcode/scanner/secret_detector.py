"""Secret detection — detect and redact secrets in file content."""

import re

REDACTION_MARKER = "[REDACTED]"

SECRET_PATTERNS = [
    re.compile(r'(API_KEY\s*=\s*)["\']?[A-Za-z0-9_\-]{16,}["\']?'),
    re.compile(r'(SECRET\s*=\s*)["\']?[A-Za-z0-9_\-]{16,}["\']?'),
    re.compile(r'(TOKEN\s*=\s*)["\']?[A-Za-z0-9_\-]{16,}["\']?'),
    re.compile(r'(PASSWORD\s*=\s*)["\']?[^"\'#\n]{4,}["\']?'),
    re.compile(r'(PRIVATE_KEY\s*=\s*)["\']?[^"\'#\n]{4,}["\']?'),
    re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----'),
]


def detect_secrets(content: str) -> tuple[str, bool]:
    safe = content
    found = False
    for pattern in SECRET_PATTERNS:
        replaced, count = pattern.subn(_redact_line, safe)
        if count > 0:
            found = True
        safe = replaced
    return safe, found


def _redact_line(m: re.Match) -> str:
    prefix = m.group(1) if m.lastindex and m.group(1) else ""
    if m.group(0).startswith("-----"):
        return REDACTION_MARKER
    return f'{prefix}"{REDACTION_MARKER}"'
