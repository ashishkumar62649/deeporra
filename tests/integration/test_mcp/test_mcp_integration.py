"""Integration tests for the MCP server — in-process protocol test.

Creates a real temp repository, indexes it, and verifies the MCP server
handles protocol messages correctly using anyio memory streams.
"""

import json
import os
import sys
import types
from pathlib import Path

import anyio
import pytest

from deeporra.chunking import Chunker
from deeporra.contracts import DeepOrraConfig, IndexState
from deeporra.embeddings import EmbeddingEncoder
from deeporra.graph.graph_builder import build_graph
from deeporra.indexing import IndexService
from deeporra.parser.python_ast import parse as parse_file
from deeporra.querying import QueryService
from deeporra.scanner.file_scanner import scan as scan_repo


class _FakeSentenceTransformer:
    def __init__(self, model_name="", device="cpu", local_files_only=True):
        pass

    def get_sentence_embedding_dimension(self):
        from deeporra.embeddings import EXPECTED_DIMENSION
        return EXPECTED_DIMENSION

    def encode(self, texts, **_):
        from deeporra.embeddings import EXPECTED_DIMENSION
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
    result = svc.build_complete_index(DeepOrraConfig(repo_path=str(repo)))
    diagnostics = [d.message for d in result.run_result.diagnostics]
    assert result.run_result.state == IndexState.COMPLETE, f"Index failed: {diagnostics}"
    return str(repo)


# ── 22. Stdio smoke test — in-process MCP protocol exchange ────────────

@pytest.mark.asyncio
async def test_mcp_stdio_smoke(indexed_repo):
    """Full protocol exchange via anyio memory streams."""
    from mcp.types import JSONRPCMessage
    from mcp.shared.session import SessionMessage

    from deeporra.mcp_server import create_mcp_server
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
    for name in ["repository_summary", "search_code", "hybrid_search",
                 "find_symbols", "find_routes", "get_related_code",
                 "analyze_change_impact", "find_existing_implementation"]:
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
    from deeporra.mcp_server import create_mcp_server
    server = create_mcp_server()
    assert server is not None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = s.connect_ex(("127.0.0.1", 8000))
    s.close()
    assert result != 0, "Port 8000 should not be open"


# ── 18. No .deeporra directory is created ─────────────────────────────────

def test_no_DEEPORRA_created(tmp_path):
    """QueryService on an unindexed root does not create .deeporra."""
    repo = tmp_path / "norepo"
    repo.mkdir()
    qs = QueryService(str(repo))
    with pytest.raises(Exception):
        qs.get_repository_summary()
    assert not (Path(str(repo)) / ".deeporra").exists()


# ── 19. No active generation is changed ────────────────────────────────

def test_no_generation_change_after_query(indexed_repo):
    """Repeated query does not change the active generation."""
    from deeporra.indexing.full_rebuild import FullRebuildCoordinator
    coord = FullRebuildCoordinator(indexed_repo)
    gen_before = coord.active_generation()

    qs = QueryService(indexed_repo)
    qs.get_repository_summary()

    gen_after = coord.active_generation()
    assert gen_before == gen_after


# ── 20. No SQLite or Chroma write occurs ───────────────────────────────

def test_no_sqlite_write_after_query(indexed_repo):
    """Query operations are read-only."""
    from deeporra.indexing.full_rebuild import FullRebuildCoordinator

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


def _is_only_broken_resource_error(exc):
    """Return True when *exc* is a BrokenResourceError (direct or
    recursively inside an ExceptionGroup) — False otherwise, so the
    caller can re-raise unexpected exceptions."""
    if isinstance(exc, anyio.BrokenResourceError):
        return True
    if hasattr(exc, "exceptions"):
        return all(_is_only_broken_resource_error(e) for e in exc.exceptions)
    return False


@pytest.mark.asyncio
async def test_hybrid_search_stdio_cold_and_warm(indexed_repo, tmp_path):
    """Real stdio server keeps semantic hybrid search available without downloads."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    bootstrap = tmp_path / "server.py"
    bootstrap.write_text(
        "import sys, types\n"
        "m = types.ModuleType('sentence_transformers')\n"
        "class SentenceTransformer:\n"
        "    def __init__(self, *args, **kwargs): pass\n"
        "    def get_sentence_embedding_dimension(self): return 384\n"
        "    def encode(self, texts, **kwargs):\n"
        "        return [[0.25] * 384 for _ in texts]\n"
        "m.SentenceTransformer = SentenceTransformer\n"
        "sys.modules['sentence_transformers'] = m\n"
        "from deeporra.mcp_server.__main__ import main\n"
        "main()\n"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(bootstrap)],
        cwd=Path.cwd(),
        env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
    )
    try:
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                with anyio.fail_after(10):
                    cold = await session.call_tool("hybrid_search", {
                        "repository_root": indexed_repo, "query": "greet", "limit": 3,
                    })
                with anyio.fail_after(10):
                    warm = await session.call_tool("hybrid_search", {
                        "repository_root": indexed_repo, "query": "greet", "limit": 3,
                    })
                with anyio.fail_after(10):
                    existing = await session.call_tool("find_existing_implementation", {
                        "repository_root": indexed_repo, "query": "greet", "limit": 3,
                    })
                assert not cold.isError and not warm.isError and not existing.isError
                results = json.loads(cold.content[0].text)
                assert results and results[0]["semantic_score"] is not None
                assert results[0]["combined_score"] is not None
    except BaseException as _exc:
        if not _is_only_broken_resource_error(_exc):
            raise
