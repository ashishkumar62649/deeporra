"""Cross-layer compatibility — real schema, real enums, real persistence."""

import os
import sqlite3
import tempfile
import uuid as uuid_mod

import pytest

from fcode.contracts.enums import (
    ChunkType,
    Confidence,
    FileType,
    GraphNodeType,
    GraphRelation,
    IndexState,
    ParseStatus,
    SearchMode,
    SymbolType,
)
from fcode.storage.migrations.v001_initial import apply as apply_migration


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_migration(conn)
    conn.commit()
    repo_id = str(uuid_mod.uuid4())
    conn.execute(
        "INSERT INTO repositories (id, path) VALUES (?, ?)",
        (repo_id, "/tmp/compat_test"),
    )
    conn.execute(
        "INSERT INTO index_status (repo_id) VALUES (?)", (repo_id,)
    )
    conn.commit()
    yield conn, repo_id
    conn.close()


def _file_id(conn):
    fid = str(uuid_mod.uuid4())
    return fid


# ── Actual-schema enum CHECK tests ─────────────────────────────────────────────


class TestFileTypeEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for i, ft in enumerate(FileType):
            fid = str(uuid_mod.uuid4())
            conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, ?, '/tmp/f.py', ?, 'pending')""",
                (fid, repo_id, f"f_{i}.py", ft.value),
            )
        conn.commit()
        cnt = conn.execute("SELECT COUNT(*) AS c FROM files WHERE repo_id = ?", (repo_id,)).fetchone()
        assert cnt["c"] == len(list(FileType))

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, 'f.py', '/tmp/f.py', 'python', 'pending')""",
                (str(uuid_mod.uuid4()), repo_id),
            )


class TestParseStatusEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for i, ps in enumerate(ParseStatus):
            fid = str(uuid_mod.uuid4())
            conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, ?, '/tmp/f.py', 'source', ?)""",
                (fid, repo_id, f"parse_{i}.py", ps.value),
            )
        conn.commit()

    def test_stored_value_matches_enum(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'f.py', '/tmp/f.py', 'source', 'parsed')""",
            (fid, repo_id),
        )
        row = conn.execute("SELECT parse_status FROM files WHERE id = ?", (fid,)).fetchone()
        assert row["parse_status"] == ParseStatus.PARSED.value

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
                   VALUES (?, ?, 'f.py', '/tmp/f.py', 'source', 'failed')""",
                (str(uuid_mod.uuid4()), repo_id),
            )


class TestSymbolTypeEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for st in SymbolType:
            conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, ?, ?)",
                (str(uuid_mod.uuid4()), repo_id, fid, st.value, f"test_{st.value}"),
            )
        conn.commit()

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 's.py', '/tmp/s.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'property', 'x')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )


class TestChunkTypeEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        for ct in ChunkType:
            conn.execute(
                "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, ?, 'content', 'c.py')",
                (str(uuid_mod.uuid4()), repo_id, fid, ct.value),
            )
        conn.commit()

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'c.py', '/tmp/c.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'code', 'content', 'c.py')",
                (str(uuid_mod.uuid4()), repo_id, fid),
            )


class TestGraphNodeTypeEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for nt in GraphNodeType:
            conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file) VALUES (?, ?, ?, ?, ?, 'f.py')",
                (str(uuid_mod.uuid4()), repo_id, f"node:{nt.value}", nt.value, nt.value),
            )
        conn.commit()

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file) VALUES (?, ?, 'n1', 'x', 'symbol', 'f.py')",
                (str(uuid_mod.uuid4()), repo_id),
            )


class TestGraphRelationEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for rel in GraphRelation:
            conn.execute(
                "INSERT INTO code_edges (id, repo_id, source_node_id, target_node_id, relation) VALUES (?, ?, 'a', 'b', ?)",
                (str(uuid_mod.uuid4()), repo_id, rel.value),
            )
        conn.commit()

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO code_edges (id, repo_id, source_node_id, target_node_id, relation) VALUES (?, ?, 'a', 'b', 'contains')",
                (str(uuid_mod.uuid4()), repo_id),
            )


class TestConfidenceEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for conf in Confidence:
            conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, ?, ?, 'file', 'f.py', ?)",
                (str(uuid_mod.uuid4()), repo_id, f"node:{conf.value}", conf.value, conf.value),
            )
        conn.commit()

    def test_stored_value_uppercase(self, db):
        conn, repo_id = db
        conn.execute(
            "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, 'n1', 'EXTRACTED', 'file', 'f.py', 'EXTRACTED')",
            (str(uuid_mod.uuid4()), repo_id),
        )
        row = conn.execute("SELECT confidence FROM code_nodes WHERE node_id = 'n1'").fetchone()
        assert row["confidence"] == "EXTRACTED"

    def test_lowercase_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, 'n2', 'x', 'file', 'f.py', 'extracted')",
                (str(uuid_mod.uuid4()), repo_id),
            )


class TestIndexStateEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for st in IndexState:
            conn.execute(
                "UPDATE index_status SET status = ? WHERE repo_id = ?",
                (st.value, repo_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT status FROM index_status WHERE repo_id = ?", (repo_id,)
            ).fetchone()
            assert row["status"] == st.value

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE index_status SET status = 'idle' WHERE repo_id = ?", (repo_id,),
            )


class TestSearchModeEnumCompatibility:
    def test_all_valid_values_insert(self, db):
        conn, repo_id = db
        for sm in SearchMode:
            conn.execute(
                "UPDATE index_status SET active_search_mode = ? WHERE repo_id = ?",
                (sm.value, repo_id),
            )
            conn.commit()

    def test_obsolete_value_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE index_status SET active_search_mode = 'exact' WHERE repo_id = ?",
                (repo_id,),
            )


# ── Real model persistence tests ──────────────────────────────────────────────


class TestRealModelPersistence:
    def test_scanned_file_persists(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'model_test.py', '/tmp/model_test.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchone()
        assert row["file_type"] == FileType.SOURCE.value
        assert row["parse_status"] == ParseStatus.PENDING.value

    def test_parsed_symbol_persists(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'sym.py', '/tmp/sym.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'my_func')",
            (sid, repo_id, fid),
        )
        row = conn.execute("SELECT * FROM symbols WHERE id = ?", (sid,)).fetchone()
        assert row["symbol_type"] == SymbolType.FUNCTION.value

    def test_code_chunk_persists(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'chunk.py', '/tmp/chunk.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        cid = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'def foo(): pass', 'chunk.py')",
            (cid, repo_id, fid),
        )
        row = conn.execute("SELECT * FROM chunks WHERE id = ?", (cid,)).fetchone()
        assert row["chunk_type"] == ChunkType.FUNCTION.value

    def test_graph_node_persists(self, db):
        conn, repo_id = db
        nid = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, 'func:foo', 'foo', 'function', 'f.py', 'EXTRACTED')",
            (nid, repo_id),
        )
        row = conn.execute("SELECT * FROM code_nodes WHERE id = ?", (nid,)).fetchone()
        assert row["node_type"] == GraphNodeType.FUNCTION.value
        assert row["confidence"] == Confidence.EXTRACTED.value

    def test_graph_edge_persists(self, db):
        conn, repo_id = db
        eid = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO code_edges (id, repo_id, source_node_id, target_node_id, relation, confidence) VALUES (?, ?, 'a', 'b', 'defines', 'EXTRACTED')",
            (eid, repo_id),
        )
        row = conn.execute("SELECT * FROM code_edges WHERE id = ?", (eid,)).fetchone()
        assert row["relation"] == GraphRelation.DEFINES.value
        assert row["confidence"] == Confidence.EXTRACTED.value

    def test_supplied_uuid_preserved(self, db):
        conn, repo_id = db
        my_uuid = "my-explicit-uuid-001"
        conn.execute(
            "INSERT INTO repositories (id, path) VALUES (?, ?)",
            (my_uuid, "/tmp/custom_uuid"),
        )
        row = conn.execute("SELECT id FROM repositories WHERE id = ?", (my_uuid,)).fetchone()
        assert row["id"] == my_uuid


# ── Real files cascade test ────────────────────────────────────────────────────


class TestFilesCascade:
    def test_delete_repository_cascades_to_files(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'cascade.py', '/tmp/cascade.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        conn.commit()
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()
        rows = conn.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchall()
        assert len(rows) == 0

    def test_orphan_symbols_deleted_with_repo(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'orphan.py', '/tmp/orphan.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        sid = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'orphan_func')",
            (sid, repo_id, fid),
        )
        conn.commit()
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()
        rows = conn.execute("SELECT * FROM symbols WHERE id = ?", (sid,)).fetchall()
        assert len(rows) == 0


# ── Real index_status test ─────────────────────────────────────────────────────


class TestIndexStatusColumns:
    def test_total_vectors_exists_and_defaults(self, db):
        conn, repo_id = db
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(index_status)").fetchall()}
        assert "total_vectors" in cols
        row = conn.execute(
            "SELECT total_vectors FROM index_status WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        assert row["total_vectors"] == 0

    def test_error_count_exists_and_defaults(self, db):
        conn, repo_id = db
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(index_status)").fetchall()}
        assert "error_count" in cols
        row = conn.execute(
            "SELECT error_count FROM index_status WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        assert row["error_count"] == 0

    def test_total_vectors_persists_nonzero(self, db):
        conn, repo_id = db
        conn.execute(
            "UPDATE index_status SET total_vectors = 42 WHERE repo_id = ?", (repo_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT total_vectors FROM index_status WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        assert row["total_vectors"] == 42

    def test_error_count_persists_nonzero(self, db):
        conn, repo_id = db
        conn.execute(
            "UPDATE index_status SET error_count = 7 WHERE repo_id = ?", (repo_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT error_count FROM index_status WHERE repo_id = ?", (repo_id,)
        ).fetchone()
        assert row["error_count"] == 7


class TestIndexStatusNotNull:
    def test_total_vectors_not_null(self, db):
        conn, repo_id = db
        col_info = conn.execute("PRAGMA table_info(index_status)").fetchall()
        col = {r["name"]: r for r in col_info}
        assert col["total_vectors"]["notnull"] == 1

    def test_total_vectors_default(self, db):
        conn, repo_id = db
        col_info = conn.execute("PRAGMA table_info(index_status)").fetchall()
        col = {r["name"]: r for r in col_info}
        dflt = col["total_vectors"]["dflt_value"]
        assert dflt == "0" or dflt == 0

    def test_error_count_not_null(self, db):
        conn, repo_id = db
        col_info = conn.execute("PRAGMA table_info(index_status)").fetchall()
        col = {r["name"]: r for r in col_info}
        assert col["error_count"]["notnull"] == 1

    def test_error_count_default(self, db):
        conn, repo_id = db
        col_info = conn.execute("PRAGMA table_info(index_status)").fetchall()
        col = {r["name"]: r for r in col_info}
        dflt = col["error_count"]["dflt_value"]
        assert dflt == "0" or dflt == 0

    def test_omitted_values_default_to_zero(self, db):
        conn, repo_id = db
        row = conn.execute(
            "SELECT total_vectors, error_count FROM index_status WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert row["total_vectors"] == 0
        assert row["error_count"] == 0

    def test_explicit_null_total_vectors_rejected(self, db):
        conn, repo_id = db
        new_id = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO repositories (id, path) VALUES (?, ?)",
            (new_id, "/tmp/null_reject"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO index_status (repo_id, total_vectors) VALUES (?, ?)",
                (new_id, None),
            )
        conn.execute("DELETE FROM repositories WHERE id = ?", (new_id,))
        conn.commit()

    def test_explicit_null_error_count_rejected(self, db):
        conn, repo_id = db
        new_id = str(uuid_mod.uuid4())
        conn.execute(
            "INSERT INTO repositories (id, path) VALUES (?, ?)",
            (new_id, "/tmp/null_reject2"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO index_status (repo_id, error_count) VALUES (?, ?)",
                (new_id, None),
            )
        conn.execute("DELETE FROM repositories WHERE id = ?", (new_id,))
        conn.commit()

    def test_update_null_total_vectors_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE index_status SET total_vectors = NULL WHERE repo_id = ?",
                (repo_id,),
            )

    def test_update_null_error_count_rejected(self, db):
        conn, repo_id = db
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE index_status SET error_count = NULL WHERE repo_id = ?",
                (repo_id,),
            )

    def test_nonzero_values_persist(self, db):
        conn, repo_id = db
        conn.execute(
            "UPDATE index_status SET total_vectors = 42, error_count = 7 WHERE repo_id = ?",
            (repo_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT total_vectors, error_count FROM index_status WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert row["total_vectors"] == 42
        assert row["error_count"] == 7


class TestNoValidEnumCausesCheckFailure:
    def test_all_nine_enums_safe(self, db):
        conn, repo_id = db
        fid = str(uuid_mod.uuid4())
        conn.execute(
            """INSERT INTO files (id, repo_id, path, absolute_path, file_type, parse_status)
               VALUES (?, ?, 'final.py', '/tmp/final.py', 'source', 'pending')""",
            (fid, repo_id),
        )
        conn.execute(
            "INSERT INTO symbols (id, repo_id, file_id, symbol_type, name) VALUES (?, ?, ?, 'function', 'safe')",
            (str(uuid_mod.uuid4()), repo_id, fid),
        )
        conn.execute(
            "INSERT INTO chunks (id, repo_id, file_id, chunk_type, content, file_path) VALUES (?, ?, ?, 'function', 'safe', 'final.py')",
            (str(uuid_mod.uuid4()), repo_id, fid),
        )
        conn.execute(
            "INSERT INTO code_nodes (id, repo_id, node_id, label, node_type, source_file, confidence) VALUES (?, ?, 'safe', 'safe', 'file', 'final.py', 'EXTRACTED')",
            (str(uuid_mod.uuid4()), repo_id),
        )
        conn.execute(
            "INSERT INTO code_edges (id, repo_id, source_node_id, target_node_id, relation) VALUES (?, ?, 'a', 'b', 'defines')",
            (str(uuid_mod.uuid4()), repo_id),
        )
        conn.execute(
            "UPDATE index_status SET status = 'pending', active_search_mode = 'fts5' WHERE repo_id = ?",
            (repo_id,),
        )
        conn.commit()
