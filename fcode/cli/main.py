"""F Code CLI — Typer application.

Registers all commands from fcode.cli.commands modules.
Contains no indexing, storage, or parsing logic.
"""

from typing import Optional

import typer

from fcode.cli.commands.index_cmd import index_cmd
from fcode.cli.commands.status_cmd import status_cmd
from fcode.cli.commands.doctor_cmd import doctor_cmd
from fcode.cli.commands.dashboard_cmd import dashboard_cmd
from fcode.cli.commands.mcp_cmd import mcp_cmd
from fcode.cli.commands.setup_cmd import setup_cmd
from fcode.contracts import IndexServiceProtocol, StatusServiceProtocol

app = typer.Typer(
    name="fcode",
    help="F Code — local-first repository intelligence tool for AI coding agents.",
    no_args_is_help=True,
)

app.command(name="index")(index_cmd)
app.command(name="status")(status_cmd)
app.command(name="doctor")(doctor_cmd)
app.command(name="dashboard")(dashboard_cmd)
app.command(name="mcp")(mcp_cmd)
app.command(name="setup")(setup_cmd)


def configure_app(
    *,
    index_service: Optional[IndexServiceProtocol] = None,
    status_service: Optional[StatusServiceProtocol] = None,
) -> None:
    """WP5 composition point: wire service implementations before CLI startup.

    Called by __main__.py before app().
    Current slice: no services wired. WP5 replaces the call with real services.
    """
    if index_service is not None:
        from fcode.cli.commands.index_cmd import set_index_service

        set_index_service(index_service)
    if status_service is not None:
        from fcode.cli.commands.status_cmd import set_status_service

        set_status_service(status_service)
