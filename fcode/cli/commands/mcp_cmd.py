"""fcode mcp --repo <path> — deferred stub (exit 2)."""

import typer


def mcp_cmd(
    repo_path: str = typer.Option(..., "--repo", help="Path to indexed repository"),
) -> None:
    """Start MCP stdio server for coding agents."""
    typer.echo("This command is not available in the first implementation slice.")
    raise typer.Exit(code=2)
