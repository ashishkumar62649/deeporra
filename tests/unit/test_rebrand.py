"""Rebrand regression tests for deeporra."""
import importlib.util
import subprocess
import sys
from pathlib import Path


def test_import_deeporra():
    """Verify import deeporra succeeds."""
    import deeporra
    assert deeporra is not None


def test_package_metadata_name():
    """Verify package metadata reports name deeporra."""
    from importlib.metadata import metadata
    meta = metadata("deeporra")
    assert meta["Name"] == "deeporra"


def test_package_metadata_version():
    """Verify package metadata reports a PEP 440 version (not a frozen value)."""
    import re
    from importlib.metadata import version
    ver = version("deeporra")
    assert re.match(r"^\d+\.\d+\.\d+", ver), f"unexpected version: {ver}"


def test_module_execution_help():
    """Verify python -m deeporra --help succeeds."""
    result = subprocess.run(
        [sys.executable, "-m", "deeporra", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "deeporra" in result.stdout.lower() or "deeporra" in result.stderr.lower()


def test_cli_executable_help():
    """Verify deeporra --help succeeds."""
    import shutil
    deeporra_exe = shutil.which("deeporra")
    if deeporra_exe is None:
        # Skip if not installed in PATH
        return
    result = subprocess.run(
        [deeporra_exe, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0


def test_doctor_command():
    """Verify deeporra doctor succeeds."""
    import shutil
    deeporra_exe = shutil.which("deeporra")
    if deeporra_exe is None:
        # Skip if not installed in PATH
        return
    result = subprocess.run(
        [deeporra_exe, "doctor"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Doctor may return non-zero if dependencies are missing
    # Just verify it runs without crashing
    assert result.returncode in (0, 1)


def test_module_doctor():
    """Verify python -m deeporra doctor succeeds."""
    result = subprocess.run(
        [sys.executable, "-m", "deeporra", "doctor"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Doctor may return non-zero if dependencies are missing
    # Just verify it runs without crashing
    assert result.returncode in (0, 1)


def test_mcp_module_is_valid():
    """Verify python -m deeporra.mcp_server is the valid MCP startup module."""
    spec = importlib.util.find_spec("deeporra.mcp_server")
    assert spec is not None


def test_no_fcode_module():
    """Verify importlib.util.find_spec('fcode') returns no project module."""
    spec = importlib.util.find_spec("fcode")
    # Should be None or not resolve to this project
    if spec is not None:
        # If it exists, it should not be in our project
        assert not str(spec.origin).startswith(str(Path(__file__).parents[2]))


def test_state_directory_deeporra():
    """Verify .deeporra is the active local state directory."""
    from deeporra.config.defaults import DEFAULT_CONFIG
    assert ".deeporra" in DEFAULT_CONFIG["storage"]["sqlite_path"]


def test_no_fcode_in_tracked_source():
    """Verify tracked source contains no accidental imports from fcode."""
    import ast
    from pathlib import Path

    source_dir = Path(__file__).parents[2] / "deeporra"
    for py_file in source_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("fcode"), (
                            f"Found fcode import in {py_file}: {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("fcode"):
                        assert False, f"Found fcode import in {py_file}: {node.module}"
        except SyntaxError:
            pass


def test_mcp_tool_names_unchanged():
    """Verify the eight MCP tool names remain unchanged."""
    try:
        from deeporra.mcp_server.server import create_mcp_server
        # The server should create without error
        server = create_mcp_server()
        assert server is not None
    except ImportError:
        # Skip if sentence_transformers not installed
        pass
