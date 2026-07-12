"""fcode status [repo_path] — show one active local index snapshot."""

from typing import Optional

import typer

from fcode.cli.dependencies import create_index_service, resolve_config
from fcode.contracts import IndexState, StatusServiceProtocol

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
    """Show the currently active complete index status."""
    try:
        config = resolve_config(repo_path)
        service = get_status_service() or create_index_service(config, for_status=True)
        status = service.get_status()
    except Exception:
        typer.echo("Status unavailable.")
        raise typer.Exit(code=1)
    if status.state == IndexState.PENDING:
        typer.echo("No active index.")
        return
    counts = status.counts
    typer.echo(f"state={status.state.value} phase={status.phase.value}")
    typer.echo(
        f"scanned={counts.scanned} parsed={counts.parsed} parse_errors={counts.parse_errors} "
        f"symbols={counts.symbols} chunks={counts.chunks} embedding_eligible={counts.embedding_eligible} "
        f"embedded={counts.embedded} embedding_skipped={counts.embedding_skipped} "
        f"embedding_failed={counts.embedding_failed} graph_nodes={counts.graph_nodes} "
        f"graph_edges={counts.graph_edges} warnings={counts.warnings} errors={counts.errors}"
    )
