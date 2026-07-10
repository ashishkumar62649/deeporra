"""Unit tests for SQLiteStore."""

import os
import sqlite3
import tempfile
import uuid as uuid_mod

import pytest

from fcode.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    s = SQLiteStore(db_path)
    s.connect()
    s.initialize_schema()
    yield s
    s.close()


@pytest.fixture
def repo_id(store):
    rid = store.create_repository_and_status("/tmp/test_repo")
    store.conn.commit()
    return rid


class TestConnection:
    def test_foreign_keys_enabled(self, store):
        row = store.conn.execute("PRAGMA foreign_keys").fetchone()
        assert row["foreign_keys"] == 1

    def test_schema_creation_succeeds(self, store):
        tables = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        expected = {
            "repositories", "files", "symbols", "chunks",
            "code_nodes", "code_edges", "index_status",
            "tool_call_logs", "repo_reports", "schema_version",
        }
        assert expected.issubset(names), f"Missing tables: {expected - names}"

    def test_schema_creation_idempotent(self, store):
        store.initialize_schema()
        store.initialize_schema()
        tables = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        assert len(tables) >= 10

    def test_schema_version_is_1(self, store):
        ver = store.get_schema_version()
        assert ver == 1

    def test_unsupported_schema_version_fails(self, store):
        store.conn.execute("UPDATE schema_version SET version = 999")
        store.conn.commit()
        with pytest.raises(ValueError, match="Unsupported schema version"):
            s2 = SQLiteStore(store._db_path)
            s2.connect()
            s2.initialize_schema()
            s2.close()


class TestTables:
    def test_every_required_table_exists(self, store):
        tables = {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for name in [
            "repositories", "files", "symbols", "chunks",
            "code_nodes", "code_edges", "index_status",
            "tool_call_logs", "repo_reports", "schema_version",
        ]:
            assert name in tables, f"Missing table: {name}"

    def test_every_required_index_exists(self, store):
        indexes = {
            r["name"]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_auto%'"
            ).fetchall()
        }
        expected = {
            "idx_files_repo", "idx_symbols_repo", "idx_symbols_name",
            "idx_symbols_file", "idx_chunks_repo", "idx_chunks_symbol",
            "idx_code_edges_source", "idx_code_edges_target",
            "idx_code_edges_relation", "idx_tool_logs_repo", "idx_reports_repo",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes: {missing}"

    def test_total_vectors_exists(self, store):
        cols = {
            r["name"]
            for r in store.conn.execute("PRAGMA table_info(index_status)").fetchall()
        }
        assert "total_vectors" in cols

    def test_error_count_exists(self, store):
        cols = {
            r["name"]
            for r in store.conn.execute("PRAGMA table_info(index_status)").fetchall()
        }
        assert "error_count" in cols


class TestCheckConstraints:
    def test_file_type_invalid(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, 'test.py', '/tmp/test.py', 'invalid_type', 'pending')""",
                (fid, repo_id),
            )

    def test_file_type_valid(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'test.py', '/tmp/test.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        store.conn.commit()

    def test_parse_status_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, 'x.py', '/tmp/x.py', 'source', 'bogus')""",
                (str(uuid_mod.uuid4()), repo_id),
            )

    def test_symbol_type_invalid(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'bogus', 'x')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )

    def test_symbol_type_valid(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for stype in ("function", "class", "method", "route", "variable"):
            sid = str(uuid_mod.uuid4())
            store.conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, ?, ?)",
                (sid, repo_id, fid, stype, f"test_{stype}"),
            )
        store.conn.commit()

    def test_chunk_type_invalid(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'bogus', 'x', 'c.py')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )

    def test_code_node_type_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file) VALUES (?, ?, 'n1', 'x', 'bogus', 'f.py')",
                (str(uuid_mod.uuid4()), repo_id),
            )

    def test_confidence_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, 'n1', 'x', 'file', 'f.py', 'bogus')",
                (str(uuid_mod.uuid4()), repo_id),
            )

    def test_relation_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO code_edges (id, repo_id, source_node_id, target_node_id, relation) VALUES (?, ?, 'a', 'b', 'bogus')",
                (str(uuid_mod.uuid4()), repo_id),
            )

    def test_index_status_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "UPDATE index_status SET status = 'bogus' WHERE repo_id = ?", (repo_id,),
            )

    def test_search_mode_invalid(self, store, repo_id):
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "UPDATE index_status SET active_search_mode = 'bogus' WHERE repo_id = ?",
                (repo_id,),
            )


class TestForeignKeys:
    def test_files_cascade_on_repo_delete(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'test.py', '/tmp/test.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        store.conn.commit()
        store.delete_repository_content(repo_id)
        store.conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        rows = store.conn.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchall()
        assert len(rows) == 0

    def test_symbols_cascade_on_file_delete(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'foo')",
            (sid, repo_id, fid),
        )
        store.conn.execute("DELETE FROM files WHERE id = ?", (fid,))
        rows = store.conn.execute("SELECT * FROM symbols WHERE id = ?", (sid,)).fetchall()
        assert len(rows) == 0

    def test_parent_symbol_set_null(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        parent_id = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'class', 'Parent')",
            (parent_id, repo_id, fid),
        )
        child_id = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name, parent_symbol_id) VALUES (?, ?, ?, 'method', 'child', ?)",
            (child_id, repo_id, fid, parent_id),
        )
        store.conn.execute("DELETE FROM symbols WHERE id = ?", (parent_id,))
        child = store.conn.execute(
            "SELECT parent_symbol_id FROM symbols WHERE id = ?", (child_id,)
        ).fetchone()
        assert child["parent_symbol_id"] is None

    def test_chunk_symbol_set_null(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sym_id = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'foo')",
            (sym_id, repo_id, fid),
        )
        cid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, symbol_id, chunk_type, content, file_path) VALUES (?, ?, ?, ?, 'function', 'x', 'c.py')",
            (cid, repo_id, fid, sym_id),
        )
        store.conn.execute("DELETE FROM symbols WHERE id = ?", (sym_id,))
        chunk = store.conn.execute(
            "SELECT symbol_id FROM chunks WHERE id = ?", (cid,)
        ).fetchone()
        assert chunk["symbol_id"] is None


class TestDuplicateAndUniqueness:
    def test_duplicate_symbol_names_allowed(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'd.py', '/tmp/d.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for _ in range(3):
            store.conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'dup_func')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )
        cnt = store.conn.execute(
            "SELECT COUNT(*) AS c FROM symbols WHERE name = 'dup_func' AND repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert cnt["c"] == 3

    def test_duplicate_qualified_names_allowed(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'q.py', '/tmp/q.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for _ in range(2):
            store.conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name, qualified_name) VALUES (?, ?, ?, 'function', 'f', 'mod.f')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )
        cnt = store.conn.execute(
            "SELECT COUNT(*) AS c FROM symbols WHERE qualified_name = 'mod.f' AND repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert cnt["c"] == 2

    def test_repository_path_unique(self, store):
        store.create_repository_and_status("/tmp/unique_test")
        with pytest.raises(sqlite3.IntegrityError):
            store.create_repository_and_status("/tmp/unique_test")

    def test_repository_id_reused(self, store):
        rid = store.create_repository_and_status("/tmp/reuse_test")
        assert rid is not None
        found = store.find_repository("/tmp/reuse_test")
        assert found == rid


class TestSuppliedUUIDs:
    def test_supplied_uuids_preserved(self, store, repo_id):
        my_uuid = "my-custom-uuid-12345"
        store.conn.execute(
            "INSERT INTO repositories (id, path) VALUES (?, ?)",
            ("other-id", "/tmp/other"),
        )
        found = store.find_repository("/tmp/other")
        assert found == "other-id"


class TestMetadataRoundTrip:
    def test_metadata_round_trip(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        import json
        meta = {"key": "value", "nested": {"a": 1}}
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'm.py', '/tmp/m.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        store.conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name, metadata) VALUES (?, ?, ?, 'function', 'foo', ?)",
            (sid, repo_id, fid, json.dumps(meta, sort_keys=True)),
        )
        row = store.conn.execute(
            "SELECT metadata FROM symbols WHERE id = ?", (sid,)
        ).fetchone()
        assert json.loads(row["metadata"]) == meta


class TestTransactionBehavior:
    def test_rollback_preserves_old_rows(self, store, repo_id):
        store.conn.execute("BEGIN")
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'r.py', '/tmp/r.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        store.conn.execute("ROLLBACK")
        rows = store.conn.execute("SELECT * FROM files WHERE repo_id = ?", (repo_id,)).fetchall()
        assert len(rows) == 0

    def test_delete_repository_content_rollback_safe(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'd.py', '/tmp/d.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        store.conn.commit()
        store.conn.execute("BEGIN")
        store.delete_repository_content(repo_id)
        store.conn.execute("ROLLBACK")
        rows = store.conn.execute("SELECT * FROM files WHERE repo_id = ?", (repo_id,)).fetchall()
        assert len(rows) == 1


class TestCleanup:
    def test_cleanup_failed_replacement(self, store, repo_id):
        fid = str(uuid_mod.uuid4())
        store.conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'f.py', '/tmp/f.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        store.conn.commit()
        store.cleanup_failed_replacement(repo_id, "test error", warning_count=2, error_count=1)
        repo = store.conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        assert repo is not None
        status = store.read_index_status(repo_id)
        assert status["status"] == "error"
        assert status["error_message"] == "test error"
        assert status["warning_count"] == 2
        assert status["error_count"] == 1
        files = store.conn.execute(
            "SELECT * FROM files WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        assert len(files) == 0


class TestParameterizedQueries:
    def test_special_characters_in_path(self, store, repo_id):
        store.conn.execute(
            "UPDATE repositories SET path = ? WHERE id = ?",
            ("path/with'quotes'and\"double\"quotes", repo_id),
        )
        store.conn.commit()
        found = store.find_repository("path/with'quotes'and\"double\"quotes")
        assert found == repo_id

    def test_error_message_length_limited(self, store, repo_id):
        long_msg = "x" * 1000
        store.update_index_status(repo_id, error_message=long_msg)
        status = store.read_index_status(repo_id)
        assert len(status["error_message"]) == 500
