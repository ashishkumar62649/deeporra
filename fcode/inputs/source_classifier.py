"""Classify a user-provided source string into local path, ZIP, GitHub URL, or reject."""

import re
from pathlib import Path

from fcode.inputs.errors import (
    InvalidRepositorySourceError,
    RepositorySourceNotFoundError,
    UnsupportedRepositoryUrlError,
)
from fcode.inputs.models import InputKind

_GITHUB_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[a-zA-Z0-9._-]+)"
    r"/"
    r"(?P<repo>[a-zA-Z0-9._-]+?)"
    r"(?:\.git)?/?$"
)

_SUPPORTED_SCHEMES = frozenset({"", "file", "zip"})


def classify(source: str) -> InputKind:
    if not source or not isinstance(source, str):
        raise InvalidRepositorySourceError(
            "Source must be a non-empty string."
        )

    source_lower = source.strip()

    if _is_github_url(source_lower):
        return InputKind.GITHUB

    p = Path(source_lower)

    if p.suffix.lower() == ".zip" and p.is_file():
        return InputKind.ZIP

    if p.is_dir():
        return InputKind.LOCAL

    if p.is_file():
        raise InvalidRepositorySourceError(
            f"Path is a regular file, not a directory or ZIP archive: {source}"
        )

    if not p.exists():
        raise RepositorySourceNotFoundError(
            f"Path does not exist: {source}"
        )

    raise InvalidRepositorySourceError(
        f"Unsupported repository source: {source}"
    )


def _is_github_url(source: str) -> bool:
    match = _GITHUB_RE.match(source)
    if match:
        return True
    if source.startswith(("http://", "https://", "git://", "ssh://")):
        raise UnsupportedRepositoryUrlError(
            f"Only public GitHub HTTPS URLs are supported: {source}"
        )
    return False


def parse_github_url(url: str) -> tuple[str, str]:
    match = _GITHUB_RE.match(url.strip())
    if not match:
        raise UnsupportedRepositoryUrlError(
            f"Invalid GitHub URL format: {url}"
        )
    return match.group("owner"), match.group("repo")


def normalize_github_url(url: str) -> str:
    owner, repo = parse_github_url(url)
    return f"https://github.com/{owner}/{repo}.git"
