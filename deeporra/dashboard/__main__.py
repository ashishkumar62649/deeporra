"""Entry point for `python -m deeporra.dashboard`."""

import sys
from pathlib import Path

from streamlit.web import cli as st_cli


def main(port: int | None = None) -> None:
    app_path = Path(__file__).resolve().parent / "app.py"
    argv = ["streamlit", "run", str(app_path), "--server.headless", "true"]
    if port is not None:
        argv.extend(["--server.port", str(port)])
    sys.argv = argv
    st_cli.main()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    args, _ = parser.parse_known_args()
    main(port=args.port)
