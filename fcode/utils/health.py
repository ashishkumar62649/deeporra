"""Offline readiness checks for the functional indexing command."""

import importlib
import sqlite3
import sys
from pathlib import Path

from fcode.contracts import DiagnosticSeverity, DoctorCheck
from fcode.contracts import DoctorResult

_REQUIRED_IMPORTS = ("sentence_transformers", "chromadb")


def check_python_version() -> DoctorCheck:
    ok = sys.version_info >= (3, 10)
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    return DoctorCheck(
        name="python_version",
        passed=ok,
        message=f"Python {ver}" if ok else f"Python 3.10+ required, found {ver}",
        severity=DiagnosticSeverity.ERROR,
    )


def check_required_imports() -> DoctorCheck:
    missing = []
    for mod in _REQUIRED_IMPORTS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return DoctorCheck(
            name="required_imports",
            passed=False,
            message=f"missing: {', '.join(missing)} (interpreter: {sys.executable})",
            severity=DiagnosticSeverity.ERROR,
        )
    return DoctorCheck(
        name="required_imports",
        passed=True,
            message=f"all available ({', '.join(_REQUIRED_IMPORTS)})",
            severity=DiagnosticSeverity.WARNING,
        )


def check_sqlite_fts5() -> DoctorCheck:
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE doctor_fts USING fts5(content)")
            conn.execute("DROP TABLE doctor_fts")
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return DoctorCheck("sqlite_fts5", False, "SQLite FTS5 is unavailable", DiagnosticSeverity.ERROR)
    return DoctorCheck("sqlite_fts5", True, "SQLite FTS5 is available", DiagnosticSeverity.WARNING)


def check_local_embedding_model() -> DoctorCheck:
    try:
        from fcode.embeddings import EmbeddingEncoder

        EmbeddingEncoder().ensure_available()
    except Exception as exc:
        return DoctorCheck(
            "local_embedding_model",
            False,
            f"Local embedding model is unavailable: {type(exc).__name__}",
            DiagnosticSeverity.ERROR,
        )
    return DoctorCheck(
        "local_embedding_model",
        True,
        "Local embedding model is available (CPU, local-only).",
        DiagnosticSeverity.WARNING,
    )


def check_directory(repo_path: str = ".") -> DoctorCheck:
    try:
        p = Path(repo_path).resolve(strict=True)
        return DoctorCheck(
            name="working_directory",
            passed=True,
            message=str(p),
            severity=DiagnosticSeverity.WARNING,
        )
    except Exception as e:
        return DoctorCheck(
            name="working_directory",
            passed=False,
            message=str(e),
            severity=DiagnosticSeverity.ERROR,
        )


def check_write_permission(repo_path: str = ".") -> DoctorCheck:
    p = Path(repo_path).resolve()
    test = p / ".fcode_dc_test"
    try:
        test.touch()
        test.unlink()
        return DoctorCheck(
            name="write_permission",
            passed=True,
            message="Directory is writable",
            severity=DiagnosticSeverity.WARNING,
        )
    except Exception as e:
        return DoctorCheck(
            name="write_permission",
            passed=False,
            message=str(e),
            severity=DiagnosticSeverity.ERROR,
        )


def check_config_parsing(repo_path: str = ".") -> DoctorCheck:
    from fcode.config.settings import CONFIG_FILE_NAME, load_config

    cfg_path = Path(repo_path) / CONFIG_FILE_NAME
    if not cfg_path.exists():
        return DoctorCheck(
            name="config_parsing",
            passed=True,
            message="No config file found, skipped",
            severity=DiagnosticSeverity.WARNING,
        )
    try:
        load_config(repo_path)
        return DoctorCheck(
            name="config_parsing",
            passed=True,
            message="Configuration is valid",
            severity=DiagnosticSeverity.WARNING,
        )
    except (ValueError, FileNotFoundError) as e:
        return DoctorCheck(
            name="config_parsing",
            passed=False,
            message=str(e),
            severity=DiagnosticSeverity.ERROR,
        )


def run_doctor(repo_path: str = ".") -> DoctorResult:
    checks = [
        check_python_version(),
        check_required_imports(),
        check_sqlite_fts5(),
        check_local_embedding_model(),
        check_directory(repo_path),
        check_write_permission(repo_path),
        check_config_parsing(repo_path),
    ]
    return DoctorResult(checks=checks)
