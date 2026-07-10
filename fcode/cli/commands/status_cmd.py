"""fcode status [repo_path] — placeholder until WP1."""

import typer
from pathlib import Path


def status_cmd(
    repo_path: str = typer.Argument(
        default=".", help="Path to indexed repository",
    ),
) -> None:
    """Show index status and stats."""
    typer.echo("Status command implementation has not started.")
    raise typer.Exit(code=1)
