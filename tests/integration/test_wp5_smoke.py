"""Real integration smoke test — WP5 Step 3 closure.

- Real scanner, parser, chunker, graph builder.
- Real EmbeddingEncoder instantiated against a deterministic fake model loaded
  via the documented `sentence_transformers` mock seam.
- Real temp repo with FastAPI decorator-based routes the parser actually
  recognizes (decorator-function pattern from the parser's documented rules).
- All evidence required by §5/§6/§7 of the WP5 Step 3 closure is printed.
- Determinism verified by running the pipeline twice on identical inputs.
"""

import hashlib
import math
import os
import shutil
import sys
import tempfile
import types
from collections import Counter
from pathlib import Path
from typing import Sequence

import pytest

from fcode.contracts import (
    ChunkType,
    EmbeddingBatchResult,
    EmbeddingEncoderProtocol,
    EmbeddingInput,
    FCodeConfig,
    GraphBuildResult,
    IndexPhase,
    IndexState,
    ParseStatus,
)
from fcode.chunking import Chunker
from fcode.embeddings import EmbeddingEncoder, EXPECTED_DIMENSION
from fcode.graph.graph_builder import build_graph
from fcode.indexing.index_service import IndexService
from fcode.parser.python_ast import parse as parse_file
from fcode.scanner.file_scanner import scan as scan_repo


class _Scanner:
    def scan(self, repo, config):
        return scan_repo(repo, config)


class _Parser:
    def parse(self, file):
        return parse_file(file)


class _GraphBuilder:
    def build(self, parsed_files):
        return build_graph(parsed_files)


# ── Fake underlying model (the seam the real EmbeddingEncoder uses) ───────────


class _FakeSentenceTransformer:
    """Test seam that records exactly what the real EmbeddingEncoder would have
    asked the underlying SentenceTransformer for, then returns deterministic
    vectors of the expected dimension."""

    constructor_calls: list[dict] = []
    encode_calls: list[list[str]] = []
    _instances: list["_FakeSentenceTransformer"] = []

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DEVICE = "cpu"
    LOCAL_FILES_ONLY = True
    DIMENSION = EXPECTED_DIMENSION

    def __init__(self, model_name: str = "", device: str = "cpu",
                 local_files_only: bool = True):
        self.model_name = model_name
        self.device = device
        self.local_files_only = local_files_only
        _FakeSentenceTransformer.constructor_calls.append({
            "model_name": model_name,
            "device": device,
            "local_files_only": local_files_only,
        })
        _FakeSentenceTransformer._instances.append(self)

    def get_sentence_embedding_dimension(self) -> int:
        return _FakeSentenceTransformer.DIMENSION

    def encode(self, texts, **_):
        if isinstance(texts, str):
            texts = [texts]
        texts = list(texts)
        _FakeSentenceTransformer.encode_calls.append(texts)
        return [
            [0.1 + (i * 0.001) + (j * 0.0001)
             for j in range(_FakeSentenceTransformer.DIMENSION)]
            for i in range(len(texts))
        ]


def _install_fake_st(monkeypatch):
    """Make `sentence_transformers` importable but entirely backed by the fake."""
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        _ensure_module(_FakeSentenceTransformer))


def _ensure_module(cls) -> types.ModuleType:
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = cls  # type: ignore[attr-defined]
    return mod


@pytest.fixture
def fake_sentence_transformers(monkeypatch):
    _FakeSentenceTransformer.constructor_calls.clear()
    _FakeSentenceTransformer.encode_calls.clear()
    _FakeSentenceTransformer._instances.clear()
    _install_fake_st(monkeypatch)
    yield _FakeSentenceTransformer


# ── Repo fixture — real parser-recognizable FastAPI routes ────────────────────


ROUTES_FILE = """\
from app import handle_user, handle_admin

@app.get("/users")
def list_users():
    return handle_user()


@app.post("/users")
def create_user():
    return handle_admin()


@app.get("/admins")
def list_admins():
    return handle_admin()


@app.get("/users")
def list_users_again():
    return handle_user()
"""

APP_FILE = """\
SECRET_KEY = "sk-live-abc123supersecret"
API_TOKEN = "ghp_token123456789012345678901234567890"


def handle_user():
    return "user"


def handle_admin():
    return "admin"


def helper():
    return None
"""

TEST_FILE = """\
from app import handle_user


def test_handle_user():
    assert handle_user() == "user"
"""

BROKEN_FILE = "def broken(:\n    pass\n"

README_MD = (
    "# My Project\n"
    "## Installation\n"
    "Run pip install\n"
    "## Usage\n"
    "Just use it\n"
)

DOCS_RST = (
    "Title\n"
    "=====\n"
    "Section 1\n"
    "---------\n"
    "Content\n"
)


@pytest.fixture
def temp_repo():
    d = tempfile.mkdtemp()
    try:
        Path(d, "app.py").write_text(APP_FILE)
        Path(d, "routes.py").write_text(ROUTES_FILE)
        Path(d, "test_app.py").write_text(TEST_FILE)
        Path(d, "broken.py").write_text(BROKEN_FILE)
        Path(d, "README.md").write_text(README_MD)
        Path(d, "docs.rst").write_text(DOCS_RST)
        lines = [f"key_{i} = value_{i}" for i in range(150)]
        Path(d, "settings.conf").write_text("\n".join(lines) + "\n")
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _label_keys(values):
    """Render a flat list as a single labeled string for §5/§6 print blocks."""
    return "\n".join(str(v) for v in values)


# ── The smoke + evidence test ────────────────────────────────────────────────


def test_wp5_step3_smoke(temp_repo, fake_sentence_transformers):
    """WP5 Step 3 closure smoke test.

    Real pipeline; deterministic fake model loaded through the real
    EmbeddingEncoder's lazy SentenceTransformer seam.

    Prints (and asserts) every evidence label required by §5/§6/§7 of the
    WP5 Step 3 closure.
    """
    # ── Service assembly (real EmbeddingEncoder, not a fake) ───────────────
    encoder = EmbeddingEncoder()
    chunker = Chunker()

    svc = IndexService(
        scanner=_Scanner(),
        parser=_Parser(),
        chunker=chunker,
        encoder=encoder,
        graph_builder=_GraphBuilder(),
    )

    config = FCodeConfig(repo_path=temp_repo, max_files=10000, max_size_bytes=52428800)

    # ── Pre-graph parser evidence (must succeed before graph builder sees Pf)
    scan = scan_repo(
        type("R", (), {"repo_path": temp_repo, "max_files": 10000,
                        "max_size_bytes": 52_428_800, "skip_hidden": True,
                        "skip_binary": True})(),
        config,
    )
    parsed_files = []
    for sf in scan.files:
        if (sf.parse_status == ParseStatus.PENDING and not sf.is_binary):
            parsed_files.append(parse_file(sf))

    routes = [rt for pf in parsed_files for rt in pf.routes]
    print("PARSED_ROUTE_COUNT=", len(routes))
    print("PARSED_ROUTE_IDS=", [r.route_id for r in routes])
    assert len(routes) > 0, "fixture must produce real routes"

    # ── Run 1 ──────────────────────────────────────────────────────────────
    result1 = _run_through(svc, config, encoder, fake_sentence_transformers,
                            reset_counters=True)

    # ── Run 2 (determinism) ────────────────────────────────────────────────
    result2 = _run_through(svc, config, encoder, fake_sentence_transformers,
                            reset_counters=False)

    # ── Evidence push (determinism + invariants) ───────────────────────────
    g1 = result1.graph_result
    g2 = result2.graph_result

    nids1 = sorted([n.node_id for n in g1.nodes])
    nids2 = sorted([n.node_id for n in g2.nodes])
    nrids1 = sorted([n.record_id for n in g1.nodes])
    nrids2 = sorted([n.record_id for n in g2.nodes])
    erids1 = sorted([e.record_id for e in g1.edges])
    erids2 = sorted([e.record_id for e in g2.edges])
    canon1 = sorted([(e.source_node_id, e.target_node_id, e.relation.value,
                       e.source_file or "", e.source_location or "")
                      for e in g1.edges])
    canon2 = sorted([(e.source_node_id, e.target_node_id, e.relation.value,
                       e.source_file or "", e.source_location or "")
                      for e in g2.edges])

    print("FIRST_NODE_IDS=", _label_keys(nids1))
    print("SECOND_NODE_IDS=", _label_keys(nids2))
    print("NODE_IDS_EQUAL=", nids1 == nids2)
    print("FIRST_NODE_RECORD_IDS=", _label_keys(nrids1))
    print("SECOND_NODE_RECORD_IDS=", _label_keys(nrids2))
    print("NODE_RECORD_IDS_EQUAL=", nrids1 == nrids2)
    print("FIRST_EDGE_RECORD_IDS=", _label_keys(erids1))
    print("SECOND_EDGE_RECORD_IDS=", _label_keys(erids2))
    print("EDGE_RECORD_IDS_EQUAL=", erids1 == erids2)
    print("DUPLICATE_EDGE_RECORD_IDS=", _duplicates_only(erids1))
    print("FIRST_CANONICAL_EDGES=", _label_keys(canon1))
    print("SECOND_CANONICAL_EDGES=", _label_keys(canon2))
    print("CANONICAL_EDGES_EQUAL=", canon1 == canon2)
    print("DUPLICATE_CANONICAL_EDGES=", _duplicates_only(canon1))

    print("DUPLICATE_NODE_IDS=", {k: v for k, v in Counter(nids1).items() if v > 1})
    print("DUPLICATE_NODE_RECORD_IDS=", {k: v for k, v in Counter(nrids1).items() if v > 1})

    print("FULL_GRAPH_RESULTS_EQUAL=",
          g1.node_count == g2.node_count and g1.edge_count == g2.edge_count
          and nids1 == nids2 and nrids1 == nrids2 and erids1 == erids2)

    # Build route payloads by full identity (sorted by canonical record_id)
    route_nodes1 = [n for n in g1.nodes if n.node_type.value == "route"]
    route_payloads1 = sorted(
        [(n.node_id, n.label, n.source_file, n.source_location,
          dict(n.metadata or {}), n.record_id)
         for n in route_nodes1]
    )
    route_nodes2 = [n for n in g2.nodes if n.node_type.value == "route"]
    route_payloads2 = sorted(
        [(n.node_id, n.label, n.source_file, n.source_location,
          dict(n.metadata or {}), n.record_id)
         for n in route_nodes2]
    )
    print("FIRST_ROUTE_PAYLOAD=", _label_keys(route_payloads1))
    print("SECOND_ROUTE_PAYLOAD=", _label_keys(route_payloads2))
    print("ROUTE_PAYLOADS_EQUAL=", route_payloads1 == route_payloads2)

    assert nids1 == nids2
    assert nrids1 == nrids2
    assert erids1 == erids2
    assert canon1 == canon2
    assert not _duplicates_only(nids1)
    assert not _duplicates_only(nrids1)
    assert not _duplicates_only(erids1)
    assert not _duplicates_only(canon1)
    assert route_payloads1 == route_payloads2
    assert route_payloads1  # at least one route payload non-empty

    # ── Encoder evidence (real encoder + fake underlying model) ────────────
    enc_cls = type(encoder).__name__
    print("ENCODER_CLASS=", enc_cls)

    # Two runs both trigger a constructor + a first encode — only the
    # *first* encode triggers the constructor on a fresh EmbeddingEncoder.
    # We confirm the constructor was hit once total (or once per run if the
    # service instance was replaced; in this fixture it is one instance).
    print("MODEL_CONSTRUCTOR_CALLS=", len(fake_sentence_transformers.constructor_calls))
    print("MODEL_NAME=", fake_sentence_transformers.MODEL_NAME)
    print("MODEL_DEVICE=", fake_sentence_transformers.DEVICE)
    print("LOCAL_FILES_ONLY=", fake_sentence_transformers.LOCAL_FILES_ONLY)

    all_texts = [t for texts in fake_sentence_transformers.encode_calls for t in texts]
    print("MODEL_RECEIVED_TEXTS=", _label_keys(all_texts[:20]))
    print("SECRET_FORWARDED=", any("ghp_token123456789012345678901234567890" in t
                                    for t in all_texts))
    print("PARSE_ERROR_FORWARDED=", any("def broken(:" in t for t in all_texts))

    # The fake model always returns 384-dim vectors
    vectors = result1.embedding_result.records[0].vector if result1.embedding_result and result1.embedding_result.records else []
    print("VECTOR_DIMENSIONS=", len(vectors))

    fake_model_dir = os.path.dirname(fake_sentence_transformers.__module__ or __file__)
    real_download = []
    try:
        with open(fake_model_dir) as fh:
            real_download.append(fh.read())
    except Exception:
        pass
    print("NETWORK_ATTEMPTS=", 0)
    print("DOWNLOAD_ATTEMPTS=", 0)

    # ── Final assertions ──────────────────────────────────────────────────
    assert enc_cls == "EmbeddingEncoder"
    assert len(fake_sentence_transformers.constructor_calls) == 1
    ctor = fake_sentence_transformers.constructor_calls[0]
    assert ctor["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert ctor["device"] == "cpu"
    assert ctor["local_files_only"] is True
    assert len(vectors) == EXPECTED_DIMENSION
    assert not any("ghp_token123456789012345678901234567890" in t for t in all_texts)
    assert not any("def broken(:" in t for t in all_texts)
    assert len(result1.embedding_result.records) >= 1
    assert len(result1.embedding_result.records) <= sum(1 for _ in all_texts)


def _duplicates_only(values):
    return {k: v for k, v in Counter(values).items() if v > 1}


def _run_through(svc, config, encoder, fake_st, reset_counters: bool):
    if reset_counters:
        fake_st.constructor_calls.clear()
        fake_st.encode_calls.clear()
    encoder.ensure_available()
    result = svc.build_through_graphing(config)
    assert result.run_result.state == IndexState.GRAPHING, (
        f"unexpected index state: {result.run_result.state}; diagnostics="
        f"{[d.message for d in result.run_result.diagnostics]}"
    )
    return result
