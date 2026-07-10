"""fcode dashboard [--port] — deferred stub (exit 2)."""

import typer


def dashboard_cmd(
    port: int = typer.Option(8501, "--port", help="Dashboard port"),
) -> None:
    """Start Streamlit dashboard on localhost."""
    typer.echo("This command is not available in the first implementation slice.")
    raise typer.Exit(code=2)
