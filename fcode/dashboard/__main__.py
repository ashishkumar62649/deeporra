"""Entry point for `python -m fcode.dashboard`."""

import sys
from pathlib import Path

from streamlit.web import cli as st_cli


def main() -> None:
    app_path = Path(__file__).resolve().parent / "app.py"
    sys.argv = ["streamlit", "run", str(app_path)]
    sys.exit(st_cli.main())


if __name__ == "__main__":
    main()
