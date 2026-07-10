"""fcode index <repo_path> — placeholder until WP5."""

import typer


def index_cmd(
    repo_path: str = typer.Argument(..., help="Path to repository to index"),
) -> None:
    """Scan, parse, embed, and build graph for a repository."""
    typer.echo("Index command implementation has not started.")
    raise typer.Exit(code=1)
