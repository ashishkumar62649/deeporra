"""fcode status [repo_path] — placeholder until WP1."""

from pathlib import Path
from typing import Optional

import typer

from fcode.contracts import StatusServiceProtocol

_status_service: Optional[StatusServiceProtocol] = None


def get_status_service() -> Optional[StatusServiceProtocol]:
    return _status_service


def set_status_service(service: StatusServiceProtocol) -> None:
    global _status_service
    _status_service = service


def status_cmd(
    repo_path: str = typer.Argument(
        default=".", help="Path to indexed repository",
    ),
) -> None:
    """Show index status and stats."""
    typer.echo("Status command implementation has not started.")
    raise typer.Exit(code=1)
