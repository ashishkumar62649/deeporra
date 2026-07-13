"""MCP-specific acceptance test — end-to-end protocol exchange.

This test creates a repository, indexes it, and verifies that the MCP server
can serve all eight tools through the MCP protocol using in-process streams.
It is the acceptance gate for Agent D's MCP implementation.
"""

import json
import sys
import types
from pathlib import Path

import anyio
import pytest

from fcode.chunking import Chunker
from fcode.contracts import FCodeConfig, IndexState
from fcode.embeddings import EmbeddingEncoder, EXPECTED_DIMENSION
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.parser.python_ast import parse as parse_file
from fcode.scanner.file_scanner import scan as scan_repo


class _FakeSentenceTransformer:
    def __init__(self, model_name="", device="cpu", local_files_only=True):
        pass

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **_):
        if isinstance(texts, str):
            texts = [texts]
        return [[0.25] * EXPECTED_DIMENSION for _ in texts]


class _RepoInput:
    def __init__(self, repo_path, max_files=10000, max_size_bytes=52428800, skip_hidden=True, skip_binary=True):
        self.repo_path = repo_path
        self.max_files = max_files
        self.max_size_bytes = max_size_bytes
        self.skip_hidden = skip_hidden
        self.skip_binary = skip_binary

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


def _write_repo(repo: Path):
    (repo / "app.py").write_text(
        "import os\n\n"
        "def util_func(x: int) -> int:\n"
        "    return x * 2\n\n"
        "class Service:\n"
        "    def process(self, data: str) -> str:\n"
        '        return f"processed: {data}"\n\n'
        "    def validate(self, data: str) -> bool:\n"
        "        return len(data) > 0\n\n"
        "@app.get('/api/items')\n"
        "def list_items():\n"
        '    return {"items": []}\n\n'
        "@app.post('/api/items')\n"
        "def create_item():\n"
        '    return {"status": "created"}\n'
    )
    (repo / "test_app.py").write_text(
        "from app import Service\n\n"
        "def test_service_process():\n"
        "    svc = Service()\n"
        '    assert svc.process("hello") == "processed: hello"\n'
    )
    (repo / "README.md").write_text("# Test\n")


@pytest.fixture
def indexed_repo(tmp_path, monkeypatch):
    _install_fake_st(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_repo(repo)
    svc = IndexService(
        _Scanner(), _Parser(), Chunker(),
        encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder(),
    )
    result = svc.build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert result.run_result.state == IndexState.COMPLETE
    return str(repo)


@pytest.mark.asyncio
async def test_mcp_acceptance_all_tools(indexed_repo):
    """End-to-end acceptance test: all seven tools respond correctly via protocol."""
    from mcp.types import JSONRPCMessage
    from mcp.shared.session import SessionMessage
    from fcode.mcp_server import create_mcp_server

    fastmcp = create_mcp_server()
    server = fastmcp._mcp_server

    to_server_send, to_server_recv = anyio.create_memory_object_stream[SessionMessage](100)
    from_server_send, from_server_recv = anyio.create_memory_object_stream[SessionMessage](100)

    responses: list = []

    async def client():
        init_msg = JSONRPCMessage(jsonrpc="2.0", id=1, method="initialize",
                                   params={"protocolVersion": "2024-11-05", "capabilities": {},
                                           "clientInfo": {"name": "test", "version": "0.1.0"}})
        await to_server_send.send(SessionMessage(message=init_msg))
        await anyio.sleep(0.1)

        notif_msg = JSONRPCMessage(jsonrpc="2.0", method="notifications/initialized")
        await to_server_send.send(SessionMessage(message=notif_msg))
        await anyio.sleep(0.1)

        calls = [
            (10, "repository_summary", {"repository_root": indexed_repo}),
            (11, "search_code", {"repository_root": indexed_repo, "query": "util_func", "mode": "text", "limit": 10}),
            (12, "hybrid_search", {"repository_root": indexed_repo, "query": "util_func", "limit": 10}),
            (13, "find_symbols", {"repository_root": indexed_repo, "query": "Service", "exact": False, "limit": 20}),
            (14, "find_routes", {"repository_root": indexed_repo, "method": "GET", "path_query": "/api", "handler_query": "", "limit": 50}),
            (15, "get_related_code", {"repository_root": indexed_repo, "semantic_key": "Service", "direction": "outgoing", "edge_types": "", "depth": 1, "limit": 100}),
            (16, "analyze_change_impact", {"repository_root": indexed_repo, "semantic_key": "util_func", "limit": 100}),
            (17, "find_existing_implementation", {"repository_root": indexed_repo, "query": "process", "limit": 10}),
        ]
        for cid, name, args in calls:
            msg = JSONRPCMessage(jsonrpc="2.0", id=cid, method="tools/call",
                                  params={"name": name, "arguments": args})
            await to_server_send.send(SessionMessage(message=msg))
            await anyio.sleep(0.1)

        await anyio.sleep(0.3)
        await to_server_send.aclose()

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
        tg.start_soon(client)
        tg.start_soon(reader)
        tg.start_soon(server_task)

    assert len(responses) >= 1

    # ── Verify initialize response ──────────────────────────────────
    r0 = responses[0]
    assert r0.root.id == 1
    assert r0.root.result is not None

    # ── Tool 1: repository_summary ──────────────────────────────────
    r1 = responses[1]
    assert r1.root.id == 10
    content_list = r1.root.result["content"]
    c0 = content_list[0]
    text = json.loads(c0["text"] if isinstance(c0, dict) else c0.text)
    assert text["index_status"] == "complete"
    assert text["file_count"] > 0

    # ── Tool 2: search_code (text) ──────────────────────────────────
    r2 = responses[2]
    assert r2.root.id == 11
    cl = r2.root.result["content"]
    results = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert len(results) >= 1
    assert results[0]["match_source"] == "text"

    # ── Tool 3: hybrid_search ───────────────────────────────────────
    r3 = responses[3]
    assert r3.root.id == 12
    cl = r3.root.result["content"]
    hresults = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert len(hresults) >= 1

    # ── Tool 4: find_symbols ────────────────────────────────────────
    r4 = responses[4]
    assert r4.root.id == 13
    cl = r4.root.result["content"]
    symbols = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert len(symbols) >= 1
    assert any("Service" in s["qualified_name"] for s in symbols)

    # ── Tool 5: find_routes ─────────────────────────────────────────
    r5 = responses[5]
    assert r5.root.id == 14
    cl = r5.root.result["content"]
    routes = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert len(routes) >= 1

    # ── Tool 6: get_related_code ────────────────────────────────────
    r6 = responses[6]
    assert r6.root.id == 15
    assert r6.root.result is not None

    # ── Tool 7: analyze_change_impact ───────────────────────────────
    r7 = responses[7]
    assert r7.root.id == 16
    cl = r7.root.result["content"]
    impact = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert impact["analysis_type"] == "first_order"

    # ── Tool 8: find_existing_implementation ────────────────────────
    r8 = responses[8]
    assert r8.root.id == 17
    cl = r8.root.result["content"]
    impl = json.loads(cl[0]["text"] if isinstance(cl[0], dict) else cl[0].text)
    assert "code_results" in impl
    assert "symbol_results" in impl
