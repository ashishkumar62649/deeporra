"""Bootstrap tests — verify repository structure and imports."""

from pathlib import Path
from fcode import __version__


class TestPackageStructure:
    def test_version(self):
        assert __version__ == "0.1.0"

    def test_contracts_package_exists(self):
        from fcode.contracts import enums, models, errors, interfaces
        assert enums is not None
        assert models is not None
        assert errors is not None
        assert interfaces is not None

    def test_cli_package_exists(self):
        from fcode.cli import main
        assert main is not None

    def test_cli_has_expected_commands(self):
        from fcode.cli.main import app
        cmds = {c.name or c.callback.__name__ for c in app.registered_commands}
        expected = {"index", "status", "doctor", "dashboard", "mcp", "setup"}
        assert cmds == expected

    def test_docs_exist(self):
        doc_dir = Path(__file__).resolve().parent.parent.parent / "docs"
        expected = [
            "01_CONTEXT.md",
            "02_PRODUCT_SPEC.md",
            "03_SYSTEM_ARCHITECTURE.md",
            "04_DATA_MODEL.md",
            "05_INDEXING_AND_RETRIEVAL.md",
            "06_MCP_TOOLS_CONTRACT.md",
            "07_DASHBOARD_SPEC.md",
            "08_SCENARIOS_AND_ACCEPTANCE_TESTS.md",
            "09_AGENT_TASKS.md",
        ]
        for name in expected:
            assert (doc_dir / name).exists(), f"Missing: {name}"

    def test_command_modules_exist(self):
        from fcode.cli.commands import (
            index_cmd,
            status_cmd,
            doctor_cmd,
            dashboard_cmd,
            mcp_cmd,
            setup_cmd,
        )
        assert index_cmd is not None
        assert status_cmd is not None
        assert doctor_cmd is not None
        assert dashboard_cmd is not None
        assert mcp_cmd is not None
        assert setup_cmd is not None
