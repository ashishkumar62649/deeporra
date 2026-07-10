"""fcode doctor — WP1 diagnostic checks."""

import typer

from fcode.contracts import DiagnosticSeverity, DoctorResult
from fcode.utils.health import run_doctor


def doctor_cmd(
    repo_path: str = typer.Argument(
        default=".", help="Path to repository to check"
    ),
) -> None:
    """Check dependencies and environment health."""
    result = run_doctor(repo_path=repo_path)
    _print_result(result)
    if not result.all_passed:
        raise typer.Exit(code=1)


def _print_result(result: DoctorResult) -> None:
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        label = f"[{status}]"
        if check.severity == DiagnosticSeverity.WARNING and check.passed:
            label = f"[{status}]"
        typer.echo(f"{label} {check.name}: {check.message}")
