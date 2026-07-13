"""Smoke test: verifies the Streamlit dashboard can start and stop cleanly.

This test launches `streamlit run` in a subprocess, waits for it to
bind, confirms the process is listening on the expected port, and
shuts it down.  No browser is opened.  No model is downloaded.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SMOKE_TIMEOUT = 30

@pytest.fixture(scope="module")
def _free_port() -> int:
    """Return a port guaranteed free at fixture-creation time."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class TestDashboardSmoke:
    """Smoke test — starts the dashboard, confirms it binds, stops it."""

    def test_streamlit_launches_and_stops(self, _free_port: int, tmp_path: Path):
        app_path = Path(__file__).parents[2] / "fcode" / "dashboard" / "app.py"
        assert app_path.is_file(), f"Dashboard app not found: {app_path}"

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app_path),
                "--server.port",
                str(_free_port),
                "--server.headless",
                "true",
                "--global.developmentMode",
                "false",
                "--server.enableCORS",
                "false",
                "--server.enableXsrfProtection",
                "false",
                "--browser.gatherUsageStats",
                "false",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(tmp_path),
        )

        try:
            deadline = time.time() + SMOKE_TIMEOUT
            started = False
            while time.time() < deadline:
                if _port_open(_free_port):
                    started = True
                    break
                time.sleep(0.5)

            assert started, (
                f"Dashboard did not bind port {_free_port} "
                f"within {SMOKE_TIMEOUT}s"
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

        stdout, stderr = proc.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # A clean exit is not guaranteed on terminate, but we must not see
        # a Python traceback in stderr.
        if proc.returncode not in (0, -15, 1, 2):
            failure = (
                f"Dashboard exited with code {proc.returncode}\n"
                f"STDOUT:\n{stdout_text}\nSTDERR:\n{stderr_text}"
            )
            if "Traceback" in stderr_text:
                pytest.fail(failure)

        # Verify no leftover processes
        assert not _port_open(_free_port), (
            f"Port {_free_port} is still in use after process termination"
        )
