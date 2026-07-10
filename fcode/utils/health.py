"""WP1 diagnostic checks for the doctor command."""

import sys
from pathlib import Path

from fcode.contracts import DiagnosticSeverity, DoctorCheck
from fcode.contracts import DoctorResult

_WP1_IMPORTS = ["typer", "pydantic"]


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
    for mod in _WP1_IMPORTS:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return DoctorCheck(
            name="required_imports",
            passed=False,
            message=f"missing: {', '.join(missing)}",
            severity=DiagnosticSeverity.ERROR,
        )
    return DoctorCheck(
        name="required_imports",
        passed=True,
        message=f"all available ({', '.join(_WP1_IMPORTS)})",
        severity=DiagnosticSeverity.WARNING,
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
        check_directory(repo_path),
        check_write_permission(repo_path),
        check_config_parsing(repo_path),
    ]
    return DoctorResult(checks=checks)
