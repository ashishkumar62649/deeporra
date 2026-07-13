"""Integration tests for dashboard â€” verifies QueryService integration through
safe wrappers using a real (indexed via fixture) repository."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from fcode.chunking.chunker import Chunker
from fcode.contracts import FCodeConfig, IndexState
from fcode.embeddings.encoder import EXPECTED_DIMENSION, EmbeddingEncoder
from fcode.graph.graph_builder import build_graph
from fcode.indexing import IndexService
from fcode.parser.python_ast import parse
from fcode.querying import RepositoryNotIndexedError, QueryService
from fcode.scanner.file_scanner import scan


class _FakeSentenceTransformer:
    def __init__(self, model_name, *, device, local_files_only):
        pass

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **_):
        return [[0.25] * EXPECTED_DIMENSION for _ in texts]


class _Scanner:
    def scan(self, repo, config):
        return scan(repo, config)


class _Parser:
    def parse(self, file):
        return parse(file)


class _GraphBuilder:
    def build(self, parsed_files):
        return build_graph(parsed_files)


def _service():
    return IndexService(
        _Scanner(), _Parser(), Chunker(),
        encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder(),
    )


def _write_small_repo(repo: Path):
    (repo / "main.py").write_text(
        "from os import path\n\n"
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}"\n\n'
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n\n"
        "    def multiply(self, a: int, b: int) -> int:\n"
        "        return a * b\n\n"
        "def main():\n"
        "    calc = Calculator()\n"
        "    print(greet('World'))\n"
        "    print(calc.add(1, 2))\n\n"
        '@app.get("/api/calc")\n'
        "def calc_route():\n"
        "    calc = Calculator()\n"
        '    return {"result": calc.add(3, 4)}\n\n'
        "API_TOKEN = 'test_only_secret'\n",
        encoding="utf-8",
    )
    (repo / "test_main.py").write_text(
        "def test_greet():\n"
        "    pass\n\n"
        "def test_calculator():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Test Repo\n\nA small test fixture.\n", encoding="utf-8")


def _index_repo(repo: Path, monkeypatch) -> str:
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    result = _service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert result.run_result.state == IndexState.COMPLETE
    return result


class TestDashboardQueryIntegration:
    """Verify safe wrappers work with a real indexed repository."""

    def test_summary_from_indexed_repo(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_small_repo(repo)
        _index_repo(repo, monkeypatch)

        from fcode.dashboard.api import safe_summary
        from fcode.querying import RepositorySummary
        qs = QueryService(str(repo))
        result = safe_summary(qs)
        assert isinstance(result, RepositorySummary)
        assert result.file_count > 0
        assert result.symbol_count > 0
        assert result.index_status == "complete"

    def test_search_from_indexed_repo(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_small_repo(repo)
        _index_repo(repo, monkeypatch)

        from fcode.dashboard.api import safe_search
        qs = QueryService(str(repo))
        results = safe_search(qs, "greet", 10, "text")
        assert isinstance(results, list)
        assert len(results) >= 1
        for r in results:
            assert not r.source_path.startswith("/")
            assert not r.source_path.startswith("\\")

    def test_search_rejects_blank(self, tmp_path):
        from fcode.dashboard.api import safe_search
        qs = QueryService(str(tmp_path))
        result = safe_search(qs, "", 10, "text")
        assert isinstance(result, str)

    def test_no_fcode_dir_returns_safe_error(self, tmp_path):
        repo = tmp_path / "nonexistent"
        repo.mkdir()
        qs = QueryService(str(repo))
        from fcode.dashboard.api import safe_summary
        result = safe_summary(qs)
        assert isinstance(result, str)
        assert "not indexed" in result.lower()

    def test_no_active_generation_returns_safe_error(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        fcode = repo / ".fcode"
        fcode.mkdir()
        (fcode / "index.db").write_text("", encoding="utf-8")
        qs = QueryService(str(repo))
        from fcode.dashboard.api import safe_summary
        result = safe_summary(qs)
        assert isinstance(result, str)
        assert "not indexed" in result.lower()

    def test_operations_do_not_write(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_small_repo(repo)
        _index_repo(repo, monkeypatch)

        fcode_dir = repo / ".fcode"
        before = {str(p.relative_to(fcode_dir)): p.stat().st_size
                  for p in fcode_dir.rglob("*") if p.is_file()}

        from fcode.dashboard.api import safe_summary, safe_search, safe_symbols, safe_routes
        qs = QueryService(str(repo))
        safe_summary(qs)
        safe_search(qs, "greet", 10, "text")
        safe_symbols(qs, "Calculator", 20, False)
        safe_routes(qs, None, None, None, 50)

        after = {str(p.relative_to(fcode_dir)): p.stat().st_size
                 for p in fcode_dir.rglob("*") if p.is_file()}
        assert before == after

    def test_paths_are_relative_not_absolute(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_small_repo(repo)
        _index_repo(repo, monkeypatch)

        from fcode.dashboard.api import safe_search, safe_symbols
        qs = QueryService(str(repo))

        results = safe_search(qs, "greet", 10, "text")
        assert isinstance(results, list)
        for r in results:
            assert not r.source_path.startswith("/")
            assert not r.source_path.startswith("\\")

        symbols = safe_symbols(qs, "Calculator", 20, False)
        assert isinstance(symbols, list)
        for s in symbols:
            assert not s.source_path.startswith("/")
            assert not s.source_path.startswith("\\")

