"""File scanner — single read-only discovery walk with eligibility rules."""

import hashlib
import os
from typing import Optional

from fcode.contracts.models import RepoInput, ScanResult, ScannedFile, SkippedFileDiagnostic
from fcode.contracts.enums import FileType, DiagnosticSeverity
from fcode.contracts.errors import ErrorCode
from fcode.scanner.ignore_rules import IgnoreRules
from fcode.scanner.secret_detector import detect_secrets


MAX_FILE_SIZE = 1_048_576

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".pyc", ".pyo", ".pyd",
    ".whl", ".egg", ".deb", ".rpm",
    ".ttf", ".otf", ".woff", ".woff2",
    ".o", ".a", ".lib", ".obj",
})

TEXT_EXTENSIONS = frozenset({
    ".py", ".pyw",
    ".md", ".rst", ".txt",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
    ".xml", ".html", ".css", ".js", ".ts", ".jsx", ".tsx",
    ".sh", ".bat", ".ps1", ".cmd",
    ".yml", ".yaml",
    ".cfg",
    ".gitignore", ".fcodeignore",
    ".dockerfile", "dockerfile",
    ".env",
})

TEST_PATH_SEGMENTS = frozenset({
    "test", "tests", "testing",
})


def _classify_file(rel_path: str) -> tuple[FileType, Optional[str]]:
    name = os.path.basename(rel_path)
    ext = os.path.splitext(name)[1].lower()

    if ext in (".py", ".pyw"):
        parts = rel_path.replace("\\", "/").split("/")
        if any(s in parts for s in TEST_PATH_SEGMENTS) or name.startswith("test_"):
            return FileType.PYTHON, "test"
        return FileType.PYTHON, "source"

    if ext in (".md", ".rst"):
        return FileType.MARKDOWN, "doc"

    if ext in (".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"):
        return FileType.CONFIG, "config"

    if name in ("Makefile", "Dockerfile", ".gitignore", ".fcodeignore",
                "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
        return FileType.CONFIG, "config"

    if ext == ".txt":
        return FileType.MARKDOWN, "doc"

    return FileType.UNKNOWN, "other"


def _is_binary_content(data: bytes) -> bool:
    return b"\0" in data[:8192]


def scan(repo: RepoInput) -> ScanResult:
    repo_path = os.path.abspath(repo.repo_path)

    if not os.path.isdir(repo_path):
        result = ScanResult(files=[], skipped=[], total_count=0, total_bytes=0)
        result.skipped.append(SkippedFileDiagnostic(
            file_path=repo_path,
            reason=f"invalid_repo_path: {repo_path} is not a directory",
            severity=DiagnosticSeverity.ERROR,
        ))
        result.total_count = 0
        return result

    ignore = IgnoreRules(repo_path)
    files: list[ScannedFile] = []
    skipped: list[SkippedFileDiagnostic] = []
    visited_dirs: set[str] = set()

    for root, dirs, entries in os.walk(repo_path, followlinks=False):
        root_rel = os.path.relpath(root, repo_path).replace("\\", "/")
        if root_rel == ".":
            root_rel = ""

        # Prune ignored/symlink directories
        filtered_dirs = []
        for d in dirs:
            dpath = os.path.join(root, d)
            drel = os.path.join(root_rel, d).replace("\\", "/") if root_rel else d

            if os.path.islink(dpath):
                skipped.append(SkippedFileDiagnostic(
                    file_path=drel,
                    reason="file_skipped: symlinked directory",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            if ignore.is_ignored(dpath):
                continue

            real = os.path.realpath(dpath)
            if real in visited_dirs:
                skipped.append(SkippedFileDiagnostic(
                    file_path=drel,
                    reason="file_skipped: symlink loop",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue
            visited_dirs.add(real)
            filtered_dirs.append(d)
        dirs[:] = filtered_dirs

        for entry in entries:
            fpath = os.path.join(root, entry)
            frel = os.path.join(root_rel, entry).replace("\\", "/") if root_rel else entry

            if IgnoreRules.is_env_file(fpath):
                continue

            if os.path.islink(fpath):
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_skipped: symlink",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            if ignore.is_ignored(fpath):
                continue

            try:
                st = os.stat(fpath)
            except OSError:
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_skipped: unreadable",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            if st.st_size > MAX_FILE_SIZE:
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_skipped: oversized",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            try:
                with open(fpath, "rb") as f:
                    raw = f.read()
            except OSError:
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_skipped: unreadable",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            ext = os.path.splitext(entry)[1].lower()
            if ext in BINARY_EXTENSIONS or _is_binary_content(raw):
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_skipped: binary",
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue

            content = raw.decode("utf-8", errors="replace")
            safe_content, has_secrets = detect_secrets(content)
            size_bytes = len(raw)
            file_type, lang = _classify_file(frel)
            sha256 = hashlib.sha256(raw).hexdigest()
            line_count = content.count("\n")
            if content and not content.endswith("\n"):
                line_count += 1

            sf = ScannedFile(
                file_path=frel,
                file_type=file_type,
                size_bytes=size_bytes,
                is_binary=False,
            )
            sf._content_hash = sha256
            sf._line_count = line_count
            sf._language = "python" if file_type == FileType.PYTHON else None
            sf._has_secrets = has_secrets
            sf._safe_content = safe_content
            sf._absolute_path = os.path.abspath(fpath)

            if has_secrets:
                skipped.append(SkippedFileDiagnostic(
                    file_path=frel,
                    reason="file_secret_detected",
                    severity=DiagnosticSeverity.WARNING,
                ))

            files.append(sf)

    files.sort(key=lambda f: (f.file_path.lower(), f.file_path))

    total_bytes = sum(f.size_bytes for f in files)
    return ScanResult(files=files, skipped=skipped, total_count=len(files), total_bytes=total_bytes)
