"""fcode index <repo_path> — placeholder until WP5."""

from typing import Optional

import typer

from fcode.contracts import IndexServiceProtocol

_index_service: Optional[IndexServiceProtocol] = None


def get_index_service() -> Optional[IndexServiceProtocol]:
    return _index_service


def set_index_service(service: IndexServiceProtocol) -> None:
    global _index_service
    _index_service = service


def index_cmd(
    repo_path: str = typer.Argument(..., help="Path to repository to index"),
) -> None:
    """Scan, parse, embed, and build graph for a repository."""
    typer.echo("Index command implementation has not started.")
    raise typer.Exit(code=1)
