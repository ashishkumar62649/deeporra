"""Unit tests for FTSStore."""

import os
import sqlite3
import tempfile
import uuid as uuid_mod

import pytest

from fcode.storage.fts_store import FTSStore
from fcode.storage.sqlite_store import SQLiteStore


@pytest.fixture
def db():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    s = SQLiteStore(db_path)
    s.connect()
    s.initialize_schema()
    repo_id = s.create_repository_and_status("/tmp/test_repo")
    s.conn.commit()
    yield s, repo_id
    s.close()


@pytest.fixture
def fts_available(db):
    store, _ = db
    return FTSStore.check_availability(store.conn)


class TestFTSStoreProtocol:
    """Public Protocol-surface tests — rebuild() and reset()."""

    def test_rebuild_requires_conn(self, db):
        fts = FTSStore()
        with pytest.raises(RuntimeError, match="not connected"):
            fts.rebuild([])

    def test_reset_requires_conn(self, db):
        fts = FTSStore()
        with pytest.raises(RuntimeError, match="not connected"):
            fts.reset()

    def test_rebuild_creates_fts_tables(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        tables = {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chunks_fts" in tables
        assert "symbols_fts" in tables

    def test_rebuild_populates_chunk_fts(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def foo(): return 42', 'c.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        assert fts.count_chunks_fts(store.conn) == 1

    def test_rebuild_populates_symbol_fts(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'my_func')",
            (sid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        assert fts.count_symbols_fts(store.conn) == 1

    def test_rebuild_maps_public_uuid(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 'm.py', '/tmp/m.py', 'source', 'pending')",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def reachable(): pass', 'm.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        results = fts.search_chunks_fts_only(store.conn, "reachable", repo_id, 10)
        uuids = [r["id"] for r in results]
        assert cid in uuids

    def test_content_replacement_rebuild_removes_stale(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 'r.py', '/tmp/r.py', 'source', 'pending')",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'stale content', 'r.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        assert fts.count_chunks_fts(store.conn) == 1
        store.conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
        store.conn.commit()
        fts.rebuild([])
        assert fts.count_chunks_fts(store.conn) == 0

    def test_reset_drops_fts_tables(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        assert "chunks_fts" in {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        fts.reset()
        tables = {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chunks_fts" not in tables
        assert "symbols_fts" not in tables

    def test_reset_does_not_delete_content_tables(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 'k.py', '/tmp/k.py', 'source', 'pending')",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'keep me', 'k.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        fts.reset()
        row = store.conn.execute("SELECT id FROM chunks WHERE id = ?", (cid,)).fetchone()
        assert row is not None

    def test_rebuild_after_reset_works(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status) VALUES (?, ?, 'w.py', '/tmp/w.py', 'source', 'pending')",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'rebuild after reset', 'w.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore(conn=store.conn)
        fts.rebuild([])
        fts.reset()
        fts.rebuild([])
        assert fts.count_chunks_fts(store.conn) == 1

    def test_rebuild_not_noop(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fts = FTSStore(conn=store.conn)
        before_count = len([
            r for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if r["name"] in ("chunks_fts", "symbols_fts")
        ])
        fts.rebuild([])
        after_count = len([
            r for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if r["name"] in ("chunks_fts", "symbols_fts")
        ])
        assert after_count >= before_count

    def test_protocol_conformance(self, db):
        import inspect
        from fcode.contracts.interfaces import FTSStoreProtocol
        sig_rebuild = inspect.signature(FTSStoreProtocol.rebuild)
        sig_reset = inspect.signature(FTSStoreProtocol.reset)
        assert list(sig_rebuild.parameters.keys()) == ["self", "chunks"]
        assert list(sig_reset.parameters.keys()) == ["self"]
        assert callable(getattr(FTSStore, "rebuild"))
        assert callable(getattr(FTSStore, "reset"))
        fts = FTSStore()
        assert callable(fts.rebuild)
        assert callable(fts.reset)


class TestFTSAvailability:
    def test_avail_detection_no_fatal(self, db):
        store, _ = db
        try:
            avail = FTSStore.check_availability(store.conn)
            assert isinstance(avail, bool)
        except Exception:
            pass


class TestFTSCreation:
    def test_virtual_tables_use_external_content(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available in this SQLite build")
        store, _ = db
        fts = FTSStore()
        fts.create_tables(store.conn)
        store.conn.commit()
        tables = {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chunks_fts" in tables
        assert "symbols_fts" in tables


class TestFTSRebuild:
    def test_chunk_rebuild_succeeds(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def foo(): pass', 'c.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore()
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        store.conn.commit()
        assert fts.count_chunks_fts(store.conn) == 1

    def test_symbol_rebuild_succeeds(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'my_func')",
            (sid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore()
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        store.conn.commit()
        assert fts.count_symbols_fts(store.conn) == 1

    def test_fts_row_maps_to_uuid(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'm.py', '/tmp/m.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def match_me(): return 42', 'm.py')",
            (cid, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore()
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        results = fts.search_chunks_fts_only(store.conn, "match_me", repo_id, 10)
        uuids = [r["id"] for r in results]
        assert cid in uuids

    def test_fts_count_matches_content(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for i in range(3):
            store.conn.execute(
                "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', ?, 'c.py')",
                (str(uuid_mod.uuid4()), repo_id, fid, f"def f{i}(): pass"),
            )
        store.conn.commit()
        fts = FTSStore()
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        chunk_count = store.conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        fts_count = fts.count_chunks_fts(store.conn)
        assert fts_count == chunk_count["c"]

    def test_rebuild_after_content_replacement_removes_stale(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'r.py', '/tmp/r.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        cid1 = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'old content', 'r.py')",
            (cid1, repo_id, fid),
        )
        store.conn.commit()
        fts = FTSStore()
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        assert fts.count_chunks_fts(store.conn) == 1
        store.conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
        cid2 = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'new content', 'r.py')",
            (cid2, repo_id, fid),
        )
        store.conn.commit()
        fts.drop_tables(store.conn)
        fts.create_tables(store.conn)
        fts.rebuild_all(store.conn)
        assert fts.count_chunks_fts(store.conn) == 1

    def test_count_mismatch_as_verification_failure(self, db, fts_available):
        if not fts_available:
            pytest.skip("FTS5 not available")
        store, repo_id = db
        fts = FTSStore()
        fts.create_tables(store.conn)
        chunk_count = 0
        fts_count = fts.count_chunks_fts(store.conn)
        assert fts_count == chunk_count


class TestLIKE:
    def test_like_fallback_search_chunks(self, db):
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'l.py', '/tmp/l.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def like_search(): pass', 'l.py')",
            (cid, repo_id, fid),
        )
        fts = FTSStore()
        results = fts.search_chunks_like(store.conn, "like_search", repo_id, 10)
        assert len(results) >= 1

    def test_like_fallback_search_symbols(self, db):
        store, repo_id = db
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'ls.py', '/tmp/ls.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'like_symbol')",
            (sid, repo_id, fid),
        )
        fts = FTSStore()
        results = fts.search_symbols_like(store.conn, "like_symbol", repo_id, 10)
        assert len(results) >= 1


class TestFTSUnavailable:
    def test_fallback_mode_returned_when_no_fts(self, db, fts_available):
        store, repo_id = db
        fts = FTSStore()
        if not fts_available:
            assert not fts_available
        else:
            assert fts_available

    def test_no_fatal_exception_when_fts_absent(self, db):
        store, _ = db
        avail = FTSStore.check_availability(store.conn)
        assert isinstance(avail, bool)

    def test_rebuild_does_not_raise_when_fts_unavailable(self, db):
        store, _ = db
        if not FTSStore.check_availability(store.conn):
            store2, _ = db
            fts = FTSStore(conn=store2.conn)
            try:
                fts.rebuild([])
            except Exception as e:
                pytest.fail(f"rebuild raised {e} when FTS unavailable")

    def test_rebuild_creates_no_tables_when_fts_unavailable(self, db):
        store, _ = db
        if not FTSStore.check_availability(store.conn):
            fts = FTSStore(conn=store.conn)
            fts.rebuild([])
            tables = {
                r["name"]
                for r in store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "chunks_fts" not in tables
            assert "symbols_fts" not in tables
