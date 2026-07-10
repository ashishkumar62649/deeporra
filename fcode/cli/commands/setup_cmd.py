"""fcode setup <agent> --repo <path> — deferred stub (exit 2)."""

import typer

_VALID_AGENTS = {"claude", "codex", "opencode"}


def setup_cmd(
    agent: str = typer.Argument(..., help="Agent name to configure"),
    repo_path: str = typer.Option(..., "--repo", help="Path to indexed repository"),
) -> None:
    """Configure agent integration."""
    if agent not in _VALID_AGENTS:
        valid = ", ".join(sorted(_VALID_AGENTS))
        typer.echo(f"Invalid agent '{agent}'. Valid agents: {valid}", err=True)
        raise typer.Exit(code=1)
    typer.echo("This command is not available in the first implementation slice.")
    raise typer.Exit(code=2)
