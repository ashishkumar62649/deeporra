"""File scanner — scan a repository for eligible files."""

import os
import hashlib

from fcode.contracts import (
    Confidence,
    DiagnosticSeverity,
    ErrorCode,
    FCodeConfig,
    FileType,
    ParseStatus,
    RepoInput,
    ScanResult,
    ScannedFile,
    SkippedFileDiagnostic,
)
from fcode.scanner.ignore_rules import IgnoreRules, HARDCODED_IGNORED_DIRS
from fcode.scanner.secret_detector import detect_secrets

MAX_ELIGIBLE_FILES = 10000
MAX_ELIGIBLE_CONTENT = 52_428_800
MAX_FILE_SIZE = 1_048_576


def scan(repo: RepoInput, config: FCodeConfig) -> ScanResult:
    return scan_repository(repo, config)


def classify_file_type(path: str) -> FileType:
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if name.startswith("test_") or name.startswith("Test") or name.endswith("_test.py") or name.endswith("Test.py"):
        return FileType.TEST
    if ext in {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf", ".xml"}:
        return FileType.CONFIG
    if ext in {".md", ".rst", ".txt", ".wiki"}:
        return FileType.DOC
    return FileType.SOURCE


def scan_repository(repo: RepoInput, config: FCodeConfig) -> ScanResult:
    repo_root = os.path.abspath(repo.repo_path)
    ignore_rules = IgnoreRules(repo_root)

    eligible: list[ScannedFile] = []
    skipped: list[SkippedFileDiagnostic] = []
    warnings: list[dict] = []
    warning_count = 0
    total_content = 0

    for dirpath, dirnames, filenames in os.walk(repo_root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, repo_root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d for d in dirnames
            if not _is_dir_ignored(os.path.join(dirpath, d), ignore_rules, rel_dir)
        ]

        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = (rel_dir + "/" + filename) if rel_dir else filename

            if ".." in rel_path.split("/") or rel_path.startswith("/"):
                continue

            if ignore_rules.is_ignored(full_path):
                skipped.append(
                    SkippedFileDiagnostic(
                        file_path=rel_path,
                        reason="ignored_by_rules",
                        details="Matched .gitignore or .fcodeignore",
                    )
                )
                continue

            skipped_diag, size = _skip_file_if_unsuitable(full_path, rel_path)
            if skipped_diag:
                skipped.append(skipped_diag)
                if skipped_diag.reason == "file_skipped" and skipped_diag.details.startswith("File too large"):
                    warning_count += 1
                    warnings.append({
                        "file_path": rel_path,
                        "code": ErrorCode.FILE_SKIPPED.value,
                        "severity": DiagnosticSeverity.WARNING.value,
                        "message": skipped_diag.details,
                    })
                continue

            if len(eligible) >= MAX_ELIGIBLE_FILES:
                skipped.append(
                    SkippedFileDiagnostic(
                        file_path=rel_path,
                        reason="repository_limit_exceeded",
                        details=f"Exceeded max {MAX_ELIGIBLE_FILES} eligible files",
                    )
                )
                total_content = MAX_ELIGIBLE_CONTENT + 1
                break

            try:
                with open(full_path, "rb") as f:
                    raw = f.read()
            except OSError:
                skipped.append(
                    SkippedFileDiagnostic(
                        file_path=rel_path,
                        reason="file_skipped",
                        details="Could not read file",
                        severity=DiagnosticSeverity.WARNING,
                    )
                )
                warning_count += 1
                warnings.append({
                    "file_path": rel_path,
                    "code": ErrorCode.FILE_SKIPPED.value,
                    "severity": DiagnosticSeverity.WARNING.value,
                    "message": "Could not read file",
                })
                continue

            if len(raw) > MAX_FILE_SIZE:
                skipped.append(
                    SkippedFileDiagnostic(
                        file_path=rel_path,
                        reason="file_skipped",
                        details=f"File too large ({len(raw)} bytes > {MAX_FILE_SIZE})",
                        severity=DiagnosticSeverity.WARNING,
                    )
                )
                warning_count += 1
                warnings.append({
                    "file_path": rel_path,
                    "code": ErrorCode.FILE_SKIPPED.value,
                    "severity": DiagnosticSeverity.WARNING.value,
                    "message": f"File too large ({len(raw)} bytes)",
                })
                continue

            content_hash = hashlib.sha256(raw).hexdigest()

            try:
                text = raw.decode("utf-8")
                is_binary = False
                line_count = text.count("\n")
                if text and not text.endswith("\n"):
                    line_count += 1
            except (UnicodeDecodeError, LookupError):
                text = ""
                is_binary = True
                line_count = 0

            safe_content, has_secrets = detect_secrets(text)
            ft = classify_file_type(full_path) if not is_binary else FileType.DOC

            if has_secrets:
                warning_count += 1
                warnings.append({
                    "file_path": rel_path,
                    "code": "file_secret_detected",
                    "severity": DiagnosticSeverity.WARNING.value,
                    "message": "Secret detected and redacted",
                })

            new_size = total_content + len(raw)
            if new_size > MAX_ELIGIBLE_CONTENT:
                skipped.append(
                    SkippedFileDiagnostic(
                        file_path=rel_path,
                        reason="repository_limit_exceeded",
                        details="Exceeded 50 MiB total eligible content",
                    )
                )
                total_content = MAX_ELIGIBLE_CONTENT + 1
                break
            total_content = new_size

            ext_lower = os.path.splitext(filename)[1].lower()
            language = "Python" if ext_lower == ".py" else None

            is_python = ext_lower == ".py"
            eligible.append(
                ScannedFile(
                    file_path=rel_path,
                    file_type=ft,
                    size_bytes=len(raw),
                    is_binary=is_binary,
                    file_id=f"file:{rel_path}",
                    absolute_path=os.path.abspath(full_path),
                    language=language,
                    has_secrets=has_secrets,
                    content_hash=content_hash,
                    parse_status=ParseStatus.PENDING if is_python else ParseStatus.NOT_APPLICABLE,
                    safe_content=safe_content,
                    line_count=line_count,
                )
            )

    eligible.sort(key=lambda f: (f.file_path.casefold(), f.file_path))
    limit_exceeded = (
        len(eligible) >= MAX_ELIGIBLE_FILES
        or total_content > MAX_ELIGIBLE_CONTENT
    )
    total_bytes = total_content if not limit_exceeded else min(total_content, MAX_ELIGIBLE_CONTENT + 1)

    return ScanResult(
        files=eligible,
        skipped=skipped,
        total_count=len(eligible),
        total_bytes=total_bytes,
        eligible_file_count=len(eligible),
        eligible_total_bytes=total_bytes,
        warnings=warnings,
        warning_count=warning_count,
    )


def _is_dir_ignored(dir_path: str, rules: IgnoreRules, rel_dir: str) -> bool:
    name = os.path.basename(dir_path)
    if name in HARDCODED_IGNORED_DIRS:
        return True
    return rules.is_ignored(dir_path)


def _skip_file_if_unsuitable(path: str, rel_path: str) -> tuple[SkippedFileDiagnostic | None, int]:
    try:
        size = os.path.getsize(path)
    except OSError:
        return SkippedFileDiagnostic(
            file_path=rel_path,
            reason="file_skipped",
            details="Cannot stat file",
            severity=DiagnosticSeverity.WARNING,
        ), 0

    if size == 0:
        return SkippedFileDiagnostic(
            file_path=rel_path,
            reason="file_skipped",
            details="Empty file",
        ), 0

    ext = os.path.splitext(path)[1].lower()
    if ext in {".exe", ".dll", ".so", ".dylib", ".bin", ".dat"}:
        return SkippedFileDiagnostic(
            file_path=rel_path,
            reason="file_skipped",
            details="Binary extension",
        ), 0

    return None, size
