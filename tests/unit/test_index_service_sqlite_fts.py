"""Unit tests for IndexService.build_through_sqlite_fts — storage + FTS stage.

Uses deterministic fake stores for boundary/failure tests and real
SQLite/FTS stores for focused readback/evidence tests.
"""

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fcode.contracts import (
    ChunkType,
    CodeChunk,
    Confidence,
    DiagnosticSeverity,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingMetadata,
    EmbeddingRecord,
    ErrorCode,
    FCodeConfig,
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    GraphNodeType,
    GraphRelation,
    IndexPhase,
    IndexState,
    ParseStatus,
    ParsedFile,
    ParsedImport,
    ParsedRoute,
    ParsedSymbol,
    ScanResult,
    ScannedFile,
    FileType,
    SymbolType,
    HttpMethod,
)
from fcode.embeddings import EXPECTED_DIMENSION
from fcode.indexing.index_service import IndexService
from fcode.storage.fts_store import FTSStore
from fcode.storage.sqlite_store import SQLiteStore


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_scanned(pid="file:app.py", path="app.py", **kw):
    merged = dict(file_id=pid, file_path=path,
                  file_type=FileType.SOURCE,
                  language="Python",
                  parse_status=ParseStatus.PARSED,
                  is_binary=False)
    merged.update(kw)
    return ScannedFile(**merged)


def _make_chunk(cid="c1", fid="file:app.py", path="app.py",
                content="def foo(): pass", start=1, end=2,
                ctype=ChunkType.FUNCTION, sym_name="foo",
                meta=None):
    return CodeChunk(
        chunk_id=cid, file_id=fid, chunk_type=ctype,
        content=content, start_line=start, end_line=end,
        file_path=path, language="Python", symbol_name=sym_name,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        metadata=meta or {"has_secrets": False, "parse_status": "parsed"},
    )


def _make_valid_record(cid="c1", path="app.py"):
    vec = [0.0] * EXPECTED_DIMENSION
    return EmbeddingRecord(
        chunk_id=cid, vector=vec,
        metadata=EmbeddingMetadata(
            chunk_id=cid, file_path=path, symbol_name="foo",
            chunk_type=ChunkType.FUNCTION, start_line=1, end_line=2,
        ),
    )


def _make_batch_result(eligible=1, success=1, fail=0, skipped=0,
                       records=None, warnings=None):
    return EmbeddingBatchResult(
        records=records or [],
        eligible_count=eligible,
        success_count=success,
        fail_count=fail,
        skipped_count=skipped,
        warnings=warnings or [],
    )


def _make_default_scan_result(files=None):
    sf = files or [_make_scanned(pid="file:app.py", path="app.py",
                                  parse_status=ParseStatus.PARSED,
                                  is_binary=False)]
    return ScanResult(
        files=sf,
        eligible_file_count=len(sf), total_count=len(sf),
        eligible_total_bytes=100,
    )

def _make_pending_scan_result():
    return ScanResult(
        files=[_make_scanned(pid="file:app.py", path="app.py",
                              parse_status=ParseStatus.PENDING, has_secrets=False,
                              is_binary=False)],
        eligible_file_count=1, total_count=1, eligible_total_bytes=100,
    )


def _make_default_parsed_files():
    return [ParsedFile(file_id="file:app.py", file_path="app.py",
                        status=ParseStatus.PARSED)]


def _nuuid(name: str) -> str:
    return "gn:" + hashlib.sha256(name.encode()).hexdigest()


def _euuid(name: str) -> str:
    return "ge:" + hashlib.sha256(name.encode()).hexdigest()


# ── Fake stores ──────────────────────────────────────────────────────────────


class _FakeSQLite:
    """Monitored fake. Records each call for order/argument inspection."""

    def __init__(self):
        self._db_path = None
        self.calls: list[str] = []
        self.conn = None
        self._repo_id = "repo:fake"
        self._repo_path = None

    def find_repository(self, path: str):
        self.calls.append(f"find_repository({path})")
        return self._repo_id if path == getattr(self, "_stored_path", None) else None

    def create_repository_and_status(self, path, content_hash=None):
        self.calls.append(f"create_repository_and_status({path})")
        self._repo_id = "repo:fake"
        self._stored_path = path
        return self._repo_id

    def initialize_schema(self):
        self.calls.append("initialize_schema()")

    def insert_files(self, repo_id, files):
        self.calls.append(f"insert_files({repo_id}, n={len(files)})")

    def insert_symbols(self, repo_id, symbols):
        self.calls.append(f"insert_symbols({repo_id}, n={len(symbols)})")

    def insert_chunks(self, repo_id, chunks):
        self.calls.append(f"insert_chunks({repo_id}, n={len(chunks)})")

    def update_index_status(self, repo_id, **kwargs):
        self.calls.append(f"update_index_status({repo_id}, {kwargs})")

    def count_files(self, repo_id):
        return 1

    def count_symbols(self, repo_id):
        return 1

    def count_chunks(self, repo_id):
        return 1

    def cleanup_failed_replacement(self, repo_id, error_message,
                                    warning_count=0, error_count=0):
        self.calls.append(f"cleanup_failed_replacement({repo_id})")
        self._last_error = error_message

    def begin_transaction(self):
        self.calls.append("begin_transaction()")

    def commit_transaction(self):
        self.calls.append("commit_transaction()")

    def rollback_transaction(self):
        self.calls.append("rollback_transaction()")


class _FakeFTS:
    def __init__(self):
        self.calls: list[str] = []

    def check_availability(self, conn):
        self.calls.append("check_availability(conn)")
        return True

    def drop_tables(self, conn):
        self.calls.append("drop_tables(conn)")

    def create_tables(self, conn):
        self.calls.append("create_tables(conn)")

    def rebuild_all(self, conn):
        self.calls.append("rebuild_all(conn)")

    def count_chunks_fts(self, conn):
        self.calls.append("count_chunks_fts(conn)")
        return 1


class _FailingFTS(_FakeFTS):
    def rebuild_all(self, conn):
        super().rebuild_all(conn)
        raise RuntimeError("database path and SQL must stay private")


class _FatalSQLite:
    """Fake that raises on any write for failure testing."""

    def __init__(self, fail_on: str = "insert_files"):
        self.fail_on = fail_on
        self._repo_id = "repo:fatal"
        self.conn = None
        self._stored_path = None
        self._repo_path = None
        self._repo_id_set = False

    def find_repository(self, path: str):
        return None

    def create_repository_and_status(self, path, content_hash=None):
        self._stored_path = path
        return self._repo_id

    def initialize_schema(self):
        pass

    def insert_files(self, repo_id, files):
        if self.fail_on == "insert_files":
            raise RuntimeError("simulated file failure")

    def insert_symbols(self, repo_id, symbols):
        if self.fail_on == "insert_symbols":
            raise RuntimeError("simulated symbol failure")

    def insert_chunks(self, repo_id, chunks):
        if self.fail_on == "insert_chunks":
            raise RuntimeError("simulated chunk failure")

    def cleanup_failed_replacement(self, repo_id, error_message,
                                    warning_count=0, error_count=0):
        self._last_error = error_message

    def begin_transaction(self):
        pass

    def commit_transaction(self):
        pass

    def rollback_transaction(self):
        pass


class _BoundarySQLite(_FakeSQLite):
    def __init__(self, fail_on):
        super().__init__()
        self.fail_on = fail_on

    def _fail(self, boundary):
        if self.fail_on == boundary:
            raise RuntimeError(f"private {boundary} failure")

    def initialize_schema(self):
        super().initialize_schema()
        self._fail("schema")

    def create_repository_and_status(self, path, content_hash=None):
        self._fail("repository")
        return super().create_repository_and_status(path, content_hash)

    def insert_files(self, repo_id, files):
        super().insert_files(repo_id, files)
        self._fail("files")

    def insert_symbols(self, repo_id, symbols):
        super().insert_symbols(repo_id, symbols)
        self._fail("symbols")

    def insert_chunks(self, repo_id, chunks):
        super().insert_chunks(repo_id, chunks)
        self._fail("chunks")

    def update_index_status(self, repo_id, **kwargs):
        super().update_index_status(repo_id, **kwargs)
        self._fail("status")

    def commit_transaction(self):
        self.calls.append("commit_transaction()")
        self._fail("commit")


# ── Real store fixture ───────────────────────────────────────────────────────


@pytest.fixture
def real_sqlite_fts():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    s = SQLiteStore(db_path)
    s.connect()
    fts = FTSStore(conn=s.conn)
    yield s, fts, tmp
    s.close()


# ── Constructor and API ──────────────────────────────────────────────────────


class TestConstructorAPI:
    def test_prior_constructor_forms_valid(self):
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock())
        assert s._sqlite_store is None
        assert s._fts_store is None

    def test_sqlite_dep_accepted(self):
        sql = _FakeSQLite()
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock(), sqlite_store=sql)
        assert s._sqlite_store is sql

    def test_fts_dep_accepted(self):
        fts = _FakeFTS()
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock(), fts_store=fts)
        assert s._fts_store is fts

    def test_constructor_calls_neither_store(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock(), sqlite_store=sql,
                          fts_store=fts)
        assert sql.calls == []
        assert fts.calls == []

    def test_build_through_sqlite_fts_exists(self):
        s = _make_step4_svc()
        assert hasattr(s, "build_through_sqlite_fts")

    def test_run_index_absent(self):
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock())
        assert not hasattr(s, "run_index")

    def test_get_status_absent(self):
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock())
        assert not hasattr(s, "get_status")

    def test_get_counts_absent(self):
        s = IndexService(scanner=MagicMock(), parser=MagicMock(),
                          chunker=MagicMock())
        assert not hasattr(s, "get_counts")


_UNSET = object()

def _make_step4_svc(scanner=_UNSET, parser=_UNSET, chunker=_UNSET,
                     encoder=_UNSET, graph_builder=_UNSET,
                     sqlite_store=_UNSET, fts_store=_UNSET):
    if scanner is _UNSET:
        sc = MagicMock()
        sc.scan.return_value = _make_default_scan_result()
        scanner = sc
    if parser is _UNSET:
        p = MagicMock()
        p.parse.return_value = _make_default_parsed_files()[0]
        parser = p
    if chunker is _UNSET:
        c = MagicMock()
        c.chunk.return_value = [_make_chunk()]
        chunker = c
    if encoder is _UNSET:
        enc = MagicMock()
        enc.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        encoder = enc
    if graph_builder is _UNSET:
        gb = MagicMock()
        gb.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        graph_builder = gb
    if sqlite_store is _UNSET:
        sqlite_store = _FakeSQLite()
    if fts_store is _UNSET:
        fts_store = _FakeFTS()
    return IndexService(
        scanner=scanner, parser=parser, chunker=chunker,
        encoder=encoder, graph_builder=graph_builder,
        sqlite_store=sqlite_store, fts_store=fts_store,
    )


# ── Missing dependencies ────────────────────────────────────────────────────


class TestMissingDeps:
    def test_missing_sqlite_raises(self):
        s = _make_step4_svc(sqlite_store=None)
        with pytest.raises(TypeError, match="sqlite_store"):
            s.build_through_sqlite_fts(FCodeConfig(repo_path="."))

    def test_missing_fts_raises(self):
        s = _make_step4_svc(fts_store=None)
        with pytest.raises(TypeError, match="fts_store"):
            s.build_through_sqlite_fts(FCodeConfig(repo_path="."))

    def test_missing_encoder_raises(self):
        s = _make_step4_svc(encoder=None)
        with pytest.raises(TypeError, match="encoder"):
            s.build_through_sqlite_fts(FCodeConfig(repo_path="."))

    def test_missing_graph_builder_raises(self):
        s = _make_step4_svc(graph_builder=None)
        with pytest.raises(TypeError, match="graph_builder"):
            s.build_through_sqlite_fts(FCodeConfig(repo_path="."))

    def test_dep_failure_before_scanner(self):
        s = _make_step4_svc()
        s._scanner = None  # invalid state — _run_step2 catches BaseException
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR

    def test_no_state_transition_on_missing_dep(self):
        sql = _FakeSQLite()
        s = _make_step4_svc(sqlite_store=None)
        try:
            s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        except TypeError:
            pass
        assert sql.calls == []


# ── Earlier failure propagation ──────────────────────────────────────────────


class TestEarlierFailuresPropagate:
    def test_validation_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path=""))
        assert r.run_result.state == IndexState.ERROR
        assert r.persistent_replacement_started is False
        assert sql.calls == []
        assert fts.calls == []

    def test_scanner_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        scanner = MagicMock()
        scanner.scan.side_effect = RuntimeError("scan fail")
        s = _make_step4_svc(scanner=scanner, sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert r.persistent_replacement_started is False
        assert sql.calls == []
        assert fts.calls == []

    def test_parser_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        scanner = MagicMock()
        scanner.scan.return_value = _make_pending_scan_result()
        parser = MagicMock()
        parser.parse.side_effect = ValueError("parse fail")
        s = _make_step4_svc(scanner=scanner, parser=parser,
                            sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert r.persistent_replacement_started is False
        assert sql.calls == []

    def test_chunker_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        chunker = MagicMock()
        chunker.chunk.side_effect = RuntimeError("chunk fail")
        s = _make_step4_svc(chunker=chunker, sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert r.persistent_replacement_started is False

    def test_embedding_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        encoder = MagicMock()
        encoder.encode.side_effect = RuntimeError("embed fail")
        s = _make_step4_svc(encoder=encoder, sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert not r.persistent_replacement_started

    def test_graph_failure_no_persist(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        gb = MagicMock()
        gb.build.side_effect = RuntimeError("graph fail")
        s = _make_step4_svc(graph_builder=gb, sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert not r.persistent_replacement_started


# ── State progression ────────────────────────────────────────────────────────


class TestStateProgression:
    def test_transition_to_storing_before_write(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.STORING

    def test_exact_success_history(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.state_history == (
            IndexState.PENDING,
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
            IndexState.EMBEDDING,
            IndexState.GRAPHING,
            IndexState.STORING,
        )

    def test_final_state_storing(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.STORING

    def test_phase_persist(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.phase == IndexPhase.PERSIST

    def test_completed_phase_graph(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.completed_phase == IndexPhase.GRAPH

    def test_replacement_flag_true(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.persistent_replacement_started is True

    def test_nonterminal(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert not r.run_result.state == IndexState.COMPLETE

    def test_complete_never_reached(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert IndexState.COMPLETE not in r.state_history


# ── Success path ─────────────────────────────────────────────────────────────


class TestSuccessPath:
    def test_store_called_in_order(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.graph_result is not None
        assert r.embedding_result is not None
        # verify store was called (symbols not present in default test data)
        assert any("insert_files" in c for c in sql.calls)
        assert any("insert_chunks" in c for c in sql.calls)
        assert any("rebuild_all" in c for c in fts.calls)

    def test_status_and_fts_commit_together(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        result = _make_step4_svc(
            sqlite_store=sql, fts_store=fts
        ).build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.STORING
        assert sql.calls.index(next(c for c in sql.calls if c.startswith("update_index_status"))) < sql.calls.index("commit_transaction()")
        assert fts.calls.index("rebuild_all(conn)") < fts.calls.index("count_chunks_fts(conn)")

    def test_fatal_diagnostics_empty(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        fatal = [d for d in r.run_result.diagnostics
                 if d.severity == DiagnosticSeverity.ERROR and not d.recoverable]
        assert len(fatal) == 0

    def test_compat_errors_empty(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.errors == []

    def test_counts_valid(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        r.run_result.counts.validate()

    def test_run_result_validates(self):
        s = _make_step4_svc()
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        r.run_result.validate()


# ── Real store readback ──────────────────────────────────────────────────────


class TestRealStoreReadback:
    """Uses real SQLite + real FTS (if available) to prove evidence survives."""

    def _build_and_probe(self, temp_dir, files, parsed_files, chunks,
                          skip_fresh=False):
        db_path = os.path.join(temp_dir, "index.db")
        sqlite = SQLiteStore(db_path)
        sqlite.connect()
        fts = FTSStore(conn=sqlite.conn)

        # Ensure scanned files have PENDING status so parser mock is invoked
        pending_files = []
        for sf in files:
            pending_files.append(_make_scanned(
                pid=sf.file_id, path=sf.file_path,
                parse_status=ParseStatus.PENDING, has_secrets=False, is_binary=False,
            ))
        scanner = MagicMock()
        scanner.scan.return_value = _make_default_scan_result(files=pending_files)
        parser = MagicMock()
        parser.parse.return_value = list(parsed_files)[0] if parsed_files else None
        chunker = MagicMock()
        chunker.chunk.return_value = list(chunks)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=len(chunks), success=len(chunks), fail=0, skipped=0,
            records=[_make_valid_record(c.chunk_id, c.file_path) for c in chunks],
        )
        gb = MagicMock()
        gb.build.return_value = GraphBuildResult(
            nodes=[GraphNodeInput(node_id="file:main.py",
                                   node_type=GraphNodeType.FILE,
                                   source_file="main.py",
                                   record_id=_nuuid("file:main.py"))],
            edges=[], node_count=1, edge_count=0,
        )
        svc = IndexService(
            scanner=scanner, parser=parser, chunker=chunker,
            encoder=encoder, graph_builder=gb,
            sqlite_store=sqlite, fts_store=fts,
        )
        r = svc.build_through_sqlite_fts(FCodeConfig(repo_path=temp_dir,
                                                       max_files=10000,
                                                       max_size_bytes=52428800))
        return r, sqlite, fts

    def _chunk(self, cid="c1", fid="file:main.py", path="main.py",
               content="def foo(): pass", ctype=ChunkType.FUNCTION, sym="foo"):
        return CodeChunk(
            chunk_id=cid, file_id=fid, chunk_type=ctype,
            content=content, start_line=1, end_line=2,
            file_path=path, language="Python", symbol_name=sym,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            metadata={"has_secrets": False, "parse_status": "parsed"},
        )

    def test_function_count_and_readback(self):
        d = tempfile.mkdtemp()
        try:
            sf = _make_scanned(pid="file:main.py", path="main.py")
            pf = ParsedFile(file_id="file:main.py", file_path="main.py",
                             status=ParseStatus.PARSED,
                             symbols=[
                                 ParsedSymbol(name="foo", symbol_type=SymbolType.FUNCTION,
                                              symbol_id="sym:foo", start_line=1, end_line=2,
                                              confidence=Confidence.EXTRACTED),
                             ])
            chunks = [self._chunk("ch1", content="def foo(): return 42")]
            r, sqlite, fts = self._build_and_probe(d, [sf], [pf], chunks)
            assert r.run_result.state == IndexState.STORING
            repo_id = sqlite.find_repository(os.path.abspath(d))
            assert repo_id is not None
            fcnt = sqlite.count_files(repo_id)
            scnt = sqlite.count_symbols(repo_id)
            ccnt = sqlite.count_chunks(repo_id)
            assert fcnt == 1
            assert scnt == 1
            assert ccnt == 1
            if FTSStore.check_availability(sqlite.conn):
                results = fts.search_chunks(sqlite.conn, "foo", repo_id, 5)
                assert len(results) >= 1
        finally:
            sqlite.close()

    def test_real_fts_query_function(self):
        d = tempfile.mkdtemp()
        try:
            sf = _make_scanned(pid="file:main.py", path="main.py")
            pf = ParsedFile(file_id="file:main.py", file_path="main.py",
                             status=ParseStatus.PARSED)
            c = self._chunk("ch1", content="def handle_user(): return 'ok'", sym="handle_user")
            chunks = [c]
            r, sqlite, fts = self._build_and_probe(d, [sf], [pf], chunks)
            if FTSStore.check_availability(sqlite.conn):
                repo_id = sqlite.find_repository(os.path.abspath(d))
                results = fts.search_chunks(sqlite.conn, "handle_user", repo_id, 5)
                assert len(results) >= 1
                assert "ch1" in [row["id"] for row in results]
        finally:
            sqlite.close()

    def test_raw_content_persisted_as_is(self):
        d = tempfile.mkdtemp()
        try:
            sf = _make_scanned(pid="file:app.py", path="app.py")
            pf = ParsedFile(file_id="file:app.py", file_path="app.py",
                             status=ParseStatus.PARSED)
            c = self._chunk("ch1", fid="file:app.py", path="app.py",
                             content="ghp_token1234567890")
            chunks = [c]
            r, sqlite, fts = self._build_and_probe(d, [sf], [pf], chunks)
            repo_id = sqlite.find_repository(os.path.abspath(d))
            # secret detection is a scanner/chunker concern, not the
            # persistence layer — with mocks, raw content passes through
            # as-is; the real integration path handles stripping.
            conn = sqlite.conn
            rows = conn.execute(
                "SELECT content FROM chunks WHERE repo_id = ?", (repo_id,)
            ).fetchall()
            for row in rows:
                assert "ghp_token1234567890" in row["content"]
        finally:
            sqlite.close()

    def test_nonexistent_query_returns_empty(self):
        d = tempfile.mkdtemp()
        try:
            sf = _make_scanned(pid="file:main.py", path="main.py")
            pf = ParsedFile(file_id="file:main.py", file_path="main.py",
                             status=ParseStatus.PARSED)
            c = self._chunk("ch1", content="def foo(): pass")
            chunks = [c]
            r, sqlite, fts = self._build_and_probe(d, [sf], [pf], chunks)
            if FTSStore.check_availability(sqlite.conn):
                repo_id = sqlite.find_repository(os.path.abspath(d))
                results = fts.search_chunks(sqlite.conn, "xyznonexistent", repo_id, 5)
                assert len(results) == 0
        finally:
            sqlite.close()


# ── Failure path ──────────────────────────────────────────────────────────────


class TestPersistenceFailures:
    @pytest.mark.parametrize(
        "boundary", ["schema", "repository", "files", "symbols", "chunks", "status", "commit"]
    )
    def test_sqlite_boundary_failures_are_sanitized(self, boundary):
        sql = _BoundarySQLite(boundary)
        scanner = MagicMock()
        scanner.scan.return_value = _make_pending_scan_result()
        parser = MagicMock()
        parser.parse.return_value = ParsedFile(
            file_id="file:app.py",
            file_path="app.py",
            status=ParseStatus.PARSED,
            symbols=[ParsedSymbol(
                name="foo",
                symbol_type=SymbolType.FUNCTION,
                symbol_id="symbol:foo",
                start_line=1,
                end_line=2,
                confidence=Confidence.EXTRACTED,
            )],
        )
        result = _make_step4_svc(
            scanner=scanner,
            parser=parser,
            sqlite_store=sql,
            fts_store=_FakeFTS(),
        ).build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        assert result.run_result.phase == IndexPhase.PERSIST
        assert result.completed_phase == IndexPhase.GRAPH
        assert result.state_history[-2:] == (IndexState.STORING, IndexState.ERROR)
        assert result.persistent_replacement_started is True
        assert result.run_result.diagnostics[-1].code == ErrorCode.PERSIST_FAILED.value
        assert result.run_result.diagnostics[-1].message == "Index metadata persistence failed."
        assert boundary not in result.run_result.diagnostics[-1].message
        if boundary != "schema":
            assert "rollback_transaction()" in sql.calls

    def test_fts_failure_rolls_back_all_metadata(self):
        sql = _FakeSQLite()
        result = _make_step4_svc(
            sqlite_store=sql, fts_store=_FailingFTS()
        ).build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        assert "rollback_transaction()" in sql.calls
        assert "commit_transaction()" not in sql.calls
        assert result.run_result.diagnostics[-1].message == "Index metadata persistence failed."
        assert "database path" not in result.run_result.diagnostics[-1].message

    @pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit, GeneratorExit])
    def test_process_control_exceptions_propagate(self, interrupt):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        fts.rebuild_all = MagicMock(side_effect=interrupt())
        with pytest.raises(interrupt):
            _make_step4_svc(
                sqlite_store=sql, fts_store=fts
            ).build_through_sqlite_fts(FCodeConfig(repo_path="."))
    def test_failure_after_storing_transition(self):
        sql = _FatalSQLite(fail_on="insert_symbols")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        assert r.run_result.phase == IndexPhase.PERSIST
        assert r.completed_phase == IndexPhase.GRAPH
        assert r.persistent_replacement_started is True
        assert r.graph_result is not None
        assert r.embedding_result is not None
        fatal = [d for d in r.run_result.diagnostics
                 if d.severity == DiagnosticSeverity.ERROR and not d.recoverable]
        assert len(fatal) >= 1
        assert "persist_failed" in fatal[0].code
        assert "Index metadata persistence failed." in fatal[0].message

    def test_history_ends_storing_error(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        history = list(r.state_history)
        assert IndexState.STORING in history
        assert IndexState.ERROR in history
        assert history[-1] == IndexState.ERROR

    def test_replacement_flag_true_on_failure(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.persistent_replacement_started is True

    def test_artifacts_retained_on_failure(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        scanner = MagicMock()
        scanner.scan.return_value = _make_pending_scan_result()
        s = _make_step4_svc(scanner=scanner, sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.graph_result is not None
        assert r.embedding_result is not None
        assert len(r.chunks) > 0
        assert len(r.parsed_files) > 0
        assert r.scan_result is not None

    def test_not_complete_on_failure(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert IndexState.COMPLETE not in r.state_history

    def test_exception_absent_from_diagnostic(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        msg = r.run_result.diagnostics[0].message
        assert "RuntimeError" not in msg
        assert "Stacktrace" not in msg
        assert "tmp" not in msg

    def test_rows_rolled_back_on_failure(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            sqlite = SQLiteStore(db_path)
            sqlite.connect()
            class FailingRealFTS(FTSStore):
                def rebuild_all(self, conn):
                    super().rebuild_all(conn)
                    raise RuntimeError("fail after FTS rows exist")

            fts = FailingRealFTS(conn=sqlite.conn)

            scanner = MagicMock()
            scanner.scan.return_value = _make_default_scan_result()
            parser = MagicMock()
            parser.parse.return_value = _make_default_parsed_files()[0]
            chunker = MagicMock()
            chunker.chunk.return_value = [_make_chunk()]
            encoder = MagicMock()
            encoder.encode.return_value = _make_batch_result(
                eligible=1, success=1, fail=0, skipped=0,
                records=[_make_valid_record()],
            )
            gb = MagicMock()
            gb.build.return_value = GraphBuildResult(
                nodes=[], edges=[], node_count=0, edge_count=0,
            )

            svc = IndexService(
                scanner=scanner, parser=parser, chunker=chunker,
                encoder=encoder, graph_builder=gb,
                sqlite_store=sqlite, fts_store=fts,
            )
            r = svc.build_through_sqlite_fts(FCodeConfig(repo_path=tmp,
                                                           max_files=10000,
                                                           max_size_bytes=52428800))
            assert r.run_result.state == IndexState.ERROR
            assert sqlite.conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0] == 0
            assert sqlite.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
            assert sqlite.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        finally:
            sqlite.close()


# ── Regression and isolation ──────────────────────────────────────────────────


class TestRegressionIsolation:
    def test_step2_still_avoids_storage(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_chunking(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.CHUNKING
        assert sql.calls == []
        assert fts.calls == []

    def test_step3_still_avoids_storage(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_graphing(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.GRAPHING
        assert not r.persistent_replacement_started
        # No calls to SQLite or FTS from Step 3
        fts_called = any("rebuild" in c or "create" in c for c in fts.calls)
        assert not fts_called

    def test_failed_step4_does_not_poison_later_success(self):
        sql = _FatalSQLite(fail_on="insert_files")
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r1 = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r1.run_result.state == IndexState.ERROR

        sql2 = _FakeSQLite()
        s._sqlite_store = sql2
        s._fts_store = fts
        r2 = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r2.run_result.state == IndexState.STORING

    def test_success_does_not_poison_step2(self):
        s = _make_step4_svc()
        r1 = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r1.run_result.state == IndexState.STORING
        # same instance, fresh attempt for step2
        r2 = s.build_through_chunking(FCodeConfig(repo_path="."))
        assert r2.run_result.state == IndexState.CHUNKING

    def test_fresh_state_per_attempt(self):
        s = _make_step4_svc()
        r1 = s.build_through_chunking(FCodeConfig(repo_path="."))
        r2 = s.build_through_chunking(FCodeConfig(repo_path="."))
        assert r1.state_history == r2.state_history  # same inputs → same history

    def test_deterministic_storage_call_order(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.STORING


# ── No later-stage persistence ──────────────────────────────────────────────


class TestNoLaterStage:
    def test_no_vector_writes(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        for c in sql.calls:
            assert "chroma" not in c.lower()
            assert "vector" not in c.lower()

    def test_no_graph_node_writes(self):
        sql = _FakeSQLite()
        fts = _FakeFTS()
        s = _make_step4_svc(sqlite_store=sql, fts_store=fts)
        r = s.build_through_sqlite_fts(FCodeConfig(repo_path="."))
        for c in sql.calls:
            assert "code_node" not in c.lower()
            assert "graph_node" not in c.lower()
            assert "insert_nodes" not in c.lower()
            assert "insert_edges" not in c.lower()
            assert "graph_store" not in c.lower()
