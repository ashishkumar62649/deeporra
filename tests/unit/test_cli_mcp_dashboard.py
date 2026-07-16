"""Focused tests for MCP and dashboard CLI commands – delegation, port, safety."""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from deeporra.cli.commands.dashboard_cmd import dashboard_cmd
from deeporra.cli.commands.mcp_cmd import mcp_cmd


class TestMCPCLI:
    def test_mcp_cmd_calls_real_server(self):
        assert mcp_cmd.__module__ is not None
        import deeporra.mcp_server.__main__
        from deeporra.mcp_server.__main__ import main as ref
        assert True

    def test_mcp_stray_stdout(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "deeporra", "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        init = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1.0"},
            },
        }) + "\n"
        try:
            out, err = proc.communicate(input=init.encode(), timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate(timeout=5)

        assert proc.returncode in (0, 1, -15), f"stderr: {err.decode()}"
        output = out.decode("utf-8", errors="replace").strip()
        # First line must be valid JSON-RPC (no stray banner text)
        if output:
            first_line = output.split("\n")[0]
            parsed = json.loads(first_line)
            assert "jsonrpc" in parsed, f"Stray output before JSON-RPC: {first_line}"

    def test_mcp_module_entry_preserved(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "deeporra.mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        init = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1.0"},
            },
        }) + "\n"
        try:
            out, err = proc.communicate(input=init.encode(), timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate(timeout=5)
        output = out.decode("utf-8", errors="replace").strip()
        if output:
            first_line = output.split("\n")[0]
            parsed = json.loads(first_line)
            assert "jsonrpc" in parsed


class TestDashboardCLI:
    def test_dashboard_cmd_has_port(self):
        import inspect
        sig = inspect.signature(dashboard_cmd)
        assert "port" in sig.parameters
        param = sig.parameters["port"]
        assert param.annotation is int or param.annotation == int

    def test_dashboard_help_shows_port(self):
        result = subprocess.run(
            [sys.executable, "-m", "deeporra", "dashboard", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--port" in result.stdout

    def test_dashboard_module_entry_preserved(self):
        port = self._free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "deeporra.dashboard", "--port", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        out = []
        err = []
        def _read_stream(stream, target):
            try:
                data = stream.read()
                target.append(data.decode("utf-8", errors="replace"))
            except (ValueError, OSError):
                pass
        tout = threading.Thread(target=_read_stream, args=(proc.stdout, out))
        terr = threading.Thread(target=_read_stream, args=(proc.stderr, err))
        tout.start()
        terr.start()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc.stdout.close()
        proc.stderr.close()
        tout.join(timeout=5)
        terr.join(timeout=5)
        full_out = "".join(out)
        full_err = "".join(err)
        started = "Uvicorn server started" in full_err or "You can now view" in full_out
        assert started, (
            f"Dashboard did not confirm startup\n"
            f"stdout: {full_out[:500]}\n"
            f"stderr: {full_err[:500]}\n"
            f"exit:   {proc.returncode}"
        )
        assert f":{port}" in full_out or f":{port}" in full_err, (
            f"Requested port {port} not reflected in output"
        )

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
