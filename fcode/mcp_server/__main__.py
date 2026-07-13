"""Entry point for python -m fcode.mcp_server."""

import asyncio
import sys

from fcode.mcp_server import create_mcp_server


def main() -> None:
    server = create_mcp_server()
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
