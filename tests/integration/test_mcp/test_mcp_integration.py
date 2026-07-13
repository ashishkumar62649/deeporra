"""Integration tests for the MCP server — in-process protocol test.

Creates a real temp repository, indexes it, and verifies the MCP server
handles protocol messages correctly using anyio memory streams.
"""

import json
import sys
import types
from pathlib import Path

import anyio
import pytest

from fcode.chunking import Chunker
from fcode.contracts import FCodeConfig, IndexState, RepoInput
from fcode.embeddings import EmbeddingEncoder
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.parser.python_ast import parse as parse_file
from fcode.querying import QueryService
from fcode.scanner.file_scanner import scan as scan_repo


class _FakeSentenceTransformer:
    def __init__(self, model_name="", device="cpu", local_files_only=True):
        pass

    def get_sentence_embedding_dimension(self):
        from fcode.embeddings import EXPECTED_DIMENSION
        return EXPECTED_DIMENSION

    def encode(self, texts, **_):
        from fcode.embeddings import EXPECTED_DIMENSION
        if isinstance(texts, str):
            texts = [texts]
        return [[0.25] * EXPECTED_DIMENSION for _ in texts]


class _Scanner:
    def scan(self, repo, config):
        return scan_repo(repo, config)


class _Parser:
    def parse(self, file):
        return parse_file(file)


class _GraphBuilder:
    def build(self, parsed_files):
        return build_graph(parsed_files)


def _install_fake_st(monkeypatch):
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


def _write_small_repo(repo: Path):
    (repo / "main.py").write_text(
        "from os import path\n"
        "\n"
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}"\n'
        "\n"
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n"
        "\n"
        "    def multiply(self, a: int, b: int) -> int:\n"
        "        return a * b\n"
        "\n"
        "def main():\n"
        "    calc = Calculator()\n"
        "    print(greet('World'))\n"
        "    print(calc.add(1, 2))\n"
        "\n"
        "@app.get('/api/calc')\n"
        "def calc_route():\n"
        "    calc = Calculator()\n"
        '    return {"result": calc.add(3, 4)}\n'
        "\n"
        "API_TOKEN = 'test_only'\n",
    )
    (repo / "test_main.py").write_text(
        "def test_greet():\n    pass\n\n"
        "def test_calculator():\n    pass\n"
    )
    (repo / "README.md").write_text("# Test Repo\n")


@pytest.fixture
def indexed_repo(tmp_path, monkeypatch):
    _install_fake_st(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_small_repo(repo)
    svc = IndexService(
        _Scanner(), _Parser(), Chunker(),
        encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder(),
    )
    result = svc.build_complete_index(FCodeConfig(repo_path=str(repo)))
    diagnostics = [d.message for d in result.run_result.diagnostics]
    assert result.run_result.state == IndexState.COMPLETE, f"Index failed: {diagnostics}"
    return str(repo)


# ── 22. Stdio smoke test — in-process MCP protocol exchange ────────────

@pytest.mark.asyncio
async def test_mcp_stdio_smoke(indexed_repo):
    """Full protocol exchange via anyio memory streams."""
    from mcp.types import JSONRPCMessage
    from mcp.shared.session import SessionMessage

    from fcode.mcp_server import create_mcp_server
    fastmcp = create_mcp_server()
    server = fastmcp._mcp_server

    to_server_send, to_server_recv = anyio.create_memory_object_stream[SessionMessage](10)
    from_server_send, from_server_recv = anyio.create_memory_object_stream[SessionMessage](10)

    responses: list = []

    async def reader():
        try:
            async for sm in from_server_recv:
                responses.append(sm.message)
        except anyio.EndOfStream:
            pass

    async def server_task():
        try:
            await server.run(
                to_server_recv, from_server_send,
                server.create_initialization_options(),
                raise_exceptions=False,
            )
        finally:
            await from_server_send.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        tg.start_soon(reader)

        # Send requests
        init_msg = JSONRPCMessage(jsonrpc="2.0", id=1, method="initialize",
                                   params={"protocolVersion": "2024-11-05", "capabilities": {},
                                           "clientInfo": {"name": "test", "version": "0.1.0"}})
        await to_server_send.send(SessionMessage(message=init_msg))

        notif_msg = JSONRPCMessage(jsonrpc="2.0", method="notifications/initialized")
        await to_server_send.send(SessionMessage(message=notif_msg))

        list_msg = JSONRPCMessage(jsonrpc="2.0", id=2, method="tools/list")
        await to_server_send.send(SessionMessage(message=list_msg))

        call_msg = JSONRPCMessage(jsonrpc="2.0", id=3, method="tools/call",
                                   params={"name": "repository_summary",
                                           "arguments": {"repository_root": indexed_repo}})
        await to_server_send.send(SessionMessage(message=call_msg))

        # Give the server time to process before closing
        await anyio.sleep(0.5)
        await to_server_send.aclose()

    for i, r in enumerate(responses):
        rt = type(r.root).__name__
        ri = getattr(r.root, 'id', None)
        print(f"Response {i}: type={rt}, id={ri}", flush=True)

    assert len(responses) >= 3, f"Expected at least 3 responses, got {len(responses)}"

    init_resp = responses[0]
    assert init_resp.root.id == 1
    assert init_resp.root.result is not None

    list_resp = responses[1]
    assert list_resp.root.id == 2
    tools_result = list_resp.root.result
    assert isinstance(tools_result, dict), f"tools_result is {type(tools_result)}: {tools_result}"
    tool_names = [t["name"] if isinstance(t, dict) else t.name for t in tools_result["tools"]]
    for name in ["repository_summary", "search_code", "find_symbols",
                  "find_routes", "get_related_code", "analyze_change_impact",
                  "find_existing_implementation"]:
        assert name in tool_names

    call_resp = responses[2]
    assert call_resp.root.id == 3
    call_result = call_resp.root.result
    assert isinstance(call_result, dict), f"call_result is {type(call_result)}: {call_result}"
    content = call_result["content"]
    assert len(content) > 0
    text = content[0]["text"] if isinstance(content[0], dict) else content[0].text
    data = json.loads(text)
    assert data.get("index_status") == "complete"
    assert data.get("file_count", 0) > 0


# ── 17. No network listener is opened ───────────────────────────────────

def test_no_network_listener():
    """Verify that server creation does not open a TCP port."""
    import socket
    from fcode.mcp_server import create_mcp_server
    server = create_mcp_server()
    assert server is not None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = s.connect_ex(("127.0.0.1", 8000))
    s.close()
    assert result != 0, "Port 8000 should not be open"


# ── 18. No .fcode directory is created ─────────────────────────────────

def test_no_fcode_created(tmp_path):
    """QueryService on an unindexed root does not create .fcode."""
    repo = tmp_path / "norepo"
    repo.mkdir()
    qs = QueryService(str(repo))
    with pytest.raises(Exception):
        qs.get_repository_summary()
    assert not (Path(str(repo)) / ".fcode").exists()


# ── 19. No active generation is changed ────────────────────────────────

def test_no_generation_change_after_query(indexed_repo):
    """Repeated query does not change the active generation."""
    from fcode.indexing.full_rebuild import FullRebuildCoordinator
    coord = FullRebuildCoordinator(indexed_repo)
    gen_before = coord.active_generation()

    qs = QueryService(indexed_repo)
    qs.get_repository_summary()

    gen_after = coord.active_generation()
    assert gen_before == gen_after


# ── 20. No SQLite or Chroma write occurs ───────────────────────────────

def test_no_sqlite_write_after_query(indexed_repo):
    """Query operations are read-only."""
    from fcode.indexing.full_rebuild import FullRebuildCoordinator

    coord = FullRebuildCoordinator(indexed_repo)
    gen = coord.active_generation()
    assert gen is not None

    db_path = Path(coord.workspace / "generations" / gen / "index.db")
    before_modified = db_path.stat().st_mtime

    qs = QueryService(indexed_repo)
    qs.get_repository_summary()
    qs.search_code("greet", limit=5, mode="text")
    qs.find_symbols("Calculator")
    qs.find_routes()

    after_modified = db_path.stat().st_mtime
    assert after_modified == before_modified


# ── 21. Repository source bytes remain unchanged ────────────────────────

def test_source_files_unchanged(indexed_repo):
    """Query operations do not modify repository sources."""
    main_py = Path(indexed_repo) / "main.py"
    before = main_py.read_bytes()

    qs = QueryService(indexed_repo)
    qs.get_repository_summary()
    qs.search_code("greet")
    qs.find_symbols("Calculator")

    after = main_py.read_bytes()
    assert before == after
