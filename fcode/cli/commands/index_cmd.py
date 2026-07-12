"""fcode index <repo_path> — build and promote one local index generation."""

from typing import Optional

import typer

from fcode.cli.dependencies import create_index_service, resolve_config
from fcode.contracts import DiagnosticSeverity, IndexServiceProtocol, IndexState

_index_service: Optional[IndexServiceProtocol] = None


def get_index_service() -> Optional[IndexServiceProtocol]:
    return _index_service


def set_index_service(service: IndexServiceProtocol) -> None:
    global _index_service
    _index_service = service


def index_cmd(
    repo_path: str = typer.Argument(".", help="Path to repository to index"),
) -> None:
    """Perform a full local rebuild of a repository index."""
    try:
        config = resolve_config(repo_path)
        service = get_index_service() or create_index_service(config)
        result = service.run_index(config)
    except Exception:
        typer.echo("Index failed.")
        raise typer.Exit(code=1)
    if result.state != IndexState.COMPLETE:
        typer.echo("Index failed.")
        for diagnostic in result.diagnostics:
            if diagnostic.severity == DiagnosticSeverity.ERROR:
                typer.echo(f"error: {diagnostic.code}: {diagnostic.message}")
        raise typer.Exit(code=1)
    counts = result.counts
    typer.echo("Index complete.")
    typer.echo(
        f"scanned={counts.scanned} parsed={counts.parsed} chunks={counts.chunks} "
        f"embedded={counts.embedded} graph_nodes={counts.graph_nodes} "
        f"graph_edges={counts.graph_edges} warnings={counts.warnings}"
    )
