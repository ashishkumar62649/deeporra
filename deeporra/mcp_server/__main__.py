"""Entry point for python -m deeporra.mcp_server."""

import asyncio

from deeporra.mcp_server import create_mcp_server


def main() -> None:
    server = create_mcp_server()
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
