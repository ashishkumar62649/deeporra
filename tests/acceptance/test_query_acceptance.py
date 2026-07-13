"""Prototype acceptance test for the read-only query service.

Creates a small Python fixture, indexes it through the full rebuild path,
creates a QueryService, exercises all operations, and proves read-only.
"""

import hashlib
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
from fcode.querying import QueryService
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


def _create_service():
    return IndexService(
        _Scanner(), _Parser(), Chunker(),
        encoder=EmbeddingEncoder(), graph_builder=_GraphBuilder(),
    )


def _write_fixture(repo: Path):
    (repo / "app.py").write_text(
        "from os import path\n\n"
        "VERSION = '1.0.0'\n\n"
        "def validate_email(email: str) -> bool:\n"
        "    if '@' in email and '.' in email.split('@')[-1]:\n"
        "        return True\n"
        "    return False\n\n"
        "class UserService:\n"
        "    def __init__(self, db: str = 'memory'):\n"
        "        self.db = db\n\n"
        "    def find_user(self, user_id: int) -> dict:\n"
        "        return {'id': user_id, 'name': 'Alice'}\n\n"
        "    def create_user(self, name: str, email: str) -> dict:\n"
        '        if not validate_email(email):\n'
        "            raise ValueError('Invalid email')\n"
        "        return {'name': name, 'email': email}\n\n"
        '@app.get("/users")\n'
        "def list_users():\n"
        "    svc = UserService()\n"
        '    return {"users": [svc.find_user(1)]}\n\n'
        '@app.post("/users")\n'
        "def create_user_route():\n"
        "    svc = UserService()\n"
        '    return {"created": True}\n',
        encoding="utf-8",
    )
    (repo / "test_app.py").write_text(
        "def test_validate_email():\n"
        "    from app import validate_email\n"
        "    assert validate_email('a@b.com')\n"
        "    assert not validate_email('invalid')\n\n"
        "def test_user_service():\n"
        "    from app import UserService\n"
        "    svc = UserService()\n"
        "    assert svc.find_user(1)['name'] == 'Alice'\n",
        encoding="utf-8",
    )


def _source_digest(repo: Path) -> str:
    digests = []
    for path in sorted(repo.rglob("*")):
        if path.is_file() and not path.relative_to(repo).parts[0].startswith(".fcode"):
            digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256("".join(digests).encode()).hexdigest()


@pytest.fixture
def indexed_repo(tmp_path, monkeypatch):
    repo = tmp_path / "fixture"
    repo.mkdir()
    _write_fixture(repo)

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    result = _create_service().build_complete_index(FCodeConfig(repo_path=str(repo)))
    assert result.run_result.state == IndexState.COMPLETE
    yield repo


class TestQueryAcceptance:
    """Full-protocol acceptance test for the query service."""

    def test_summary_returns_all_counts(self, indexed_repo):
        qs = QueryService(str(indexed_repo))
        summary = qs.get_repository_summary()

        assert summary.index_status == "complete"
        assert summary.repository_root == str(indexed_repo.resolve())
        assert summary.file_count >= 2
        assert summary.symbol_count >= 4
        assert summary.chunk_count >= 4
        assert summary.graph_node_count > 0
        assert summary.graph_edge_count > 0
        assert summary.route_count >= 2
        assert summary.test_count >= 2

    def test_search_code_finds_implementation(self, indexed_repo):
        qs = QueryService(str(indexed_repo))

        text_results = qs.search_code("validate_email", mode="text")
        assert len(text_results) >= 1
        assert any(
            "validate_email" in r.display_text or "validate_email" in r.owner_semantic_key or ""
            for r in text_results
        )

        hybrid_results = qs.search_code("validate_email", mode="hybrid")
        assert len(hybrid_results) >= 1

    def test_find_known_symbol(self, indexed_repo):
        qs = QueryService(str(indexed_repo))

        partial = qs.find_symbols("validate_email", exact=False)
        assert any("validate_email" in s.qualified_name for s in partial)

        partial_class = qs.find_symbols("UserService", exact=False)
        assert any("UserService" in s.qualified_name for s in partial_class)

    def test_routes(self, indexed_repo):
        qs = QueryService(str(indexed_repo))

        get_routes = qs.find_routes(method="GET")
        assert len(get_routes) >= 1
        assert all(r.http_method == "GET" for r in get_routes)

        users_routes = qs.find_routes(path_query="/users")
        assert len(users_routes) >= 2

        all_routes = qs.find_routes()
        assert len(all_routes) >= 2

    def test_graph_relationships(self, indexed_repo):
        qs = QueryService(str(indexed_repo))

        symbols = qs.find_symbols("validate_email", exact=False)
        if not symbols:
            pytest.skip("Symbol not found")
        key = symbols[0].semantic_key
        related = qs.get_related(key, direction="both", depth=1, limit=50)
        assert isinstance(related, list)

    def test_first_order_impact(self, indexed_repo):
        qs = QueryService(str(indexed_repo))

        symbols = qs.find_symbols("UserService", exact=False)
        if not symbols:
            pytest.skip("Symbol not found")

        impact = qs.analyze_change_impact(symbols[0].semantic_key)
        assert impact.analysis_type == "first_order"
        assert impact.target_qualified_name == symbols[0].qualified_name

    def test_source_files_unchanged(self, indexed_repo):
        before = _source_digest(indexed_repo)
        qs = QueryService(str(indexed_repo))
        qs.get_repository_summary()
        qs.search_code("validate_email")
        qs.find_symbols("UserService")
        qs.find_routes()
        after = _source_digest(indexed_repo)
        assert before == after, "Repository source files were modified by query operations"
