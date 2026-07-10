"""Unit tests for GraphStore."""

import os
import sqlite3
import tempfile
import uuid as uuid_mod

import pytest

from fcode.storage.graph_store import GraphStore, _json_dumps
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


class TestGraphStore:
    def test_nodes_insert_and_count(self, db):
        store, repo_id = db
        gs = GraphStore()
        nodes = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": "file:test.py",
                "label": "test.py",
                "node_type": "file",
                "source_file": "test.py",
                "source_location": None,
                "confidence": "EXTRACTED",
            }
        ]
        gs.insert_nodes(store.conn, repo_id, nodes)
        assert gs.count_nodes(store.conn, repo_id) == 1

    def test_edges_insert_and_count(self, db):
        store, repo_id = db
        gs = GraphStore()
        nodes = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": "file:a.py",
                "label": "a.py",
                "node_type": "file",
                "source_file": "a.py",
                "confidence": "EXTRACTED",
            },
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": "import:os",
                "label": "os",
                "node_type": "import",
                "source_file": "a.py",
                "confidence": "EXTRACTED",
            },
        ]
        gs.insert_nodes(store.conn, repo_id, nodes)
        edges = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "source_node_id": "file:a.py",
                "target_node_id": "import:os",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
            }
        ]
        gs.insert_edges(store.conn, repo_id, edges)
        assert gs.count_edges(store.conn, repo_id) == 1

    def test_duplicate_logical_node_rejected(self, db):
        store, repo_id = db
        gs = GraphStore()
        nid = "unique:test"
        nodes = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": nid,
                "label": "test",
                "node_type": "function",
                "source_file": "test.py",
                "confidence": "EXTRACTED",
            },
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": nid,
                "label": "test",
                "node_type": "function",
                "source_file": "test.py",
                "confidence": "EXTRACTED",
            },
        ]
        gs.insert_nodes(store.conn, repo_id, [nodes[0]])
        with pytest.raises(sqlite3.IntegrityError):
            gs.insert_nodes(store.conn, repo_id, [nodes[1]])

    def test_same_node_id_different_repos_allowed(self, db):
        store, repo_id1 = db
        gs = GraphStore()
        repo_id2 = store.create_repository_and_status("/tmp/other_repo")
        nid = "shared:node"
        for rid in (repo_id1, repo_id2):
            gs.insert_nodes(store.conn, rid, [
                {
                    "id": str(uuid_mod.uuid4()),
                    "repo_id": rid,
                    "node_id": nid,
                    "label": "shared",
                    "node_type": "function",
                    "source_file": "s.py",
                    "confidence": "EXTRACTED",
                },
            ])
        assert gs.count_nodes(store.conn, repo_id1) == 1
        assert gs.count_nodes(store.conn, repo_id2) == 1

    def test_multiple_edges_same_source_target_relation_different_evidence(self, db):
        store, repo_id = db
        gs = GraphStore()
        n1 = str(uuid_mod.uuid4())
        n2 = str(uuid_mod.uuid4())
        gs.insert_nodes(store.conn, repo_id, [
            {"id": n1, "repo_id": repo_id, "node_id": "file:a.py", "label": "a.py", "node_type": "file", "source_file": "a.py", "confidence": "EXTRACTED"},
            {"id": n2, "repo_id": repo_id, "node_id": "import:os", "label": "os", "node_type": "import", "source_file": "a.py", "confidence": "EXTRACTED"},
        ])
        edges = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "source_node_id": "file:a.py",
                "target_node_id": "import:os",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "metadata": '{"line_number": 1}',
            },
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "source_node_id": "file:a.py",
                "target_node_id": "import:os",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "b.py",
                "metadata": '{"line_number": 5}',
            },
        ]
        gs.insert_edges(store.conn, repo_id, edges)
        assert gs.count_edges(store.conn, repo_id) == 2

    def test_no_graph_traversal(self, db):
        store, repo_id = db
        gs = GraphStore()
        assert hasattr(gs, "insert_nodes")
        assert not hasattr(gs, "traverse")

    def test_no_relationship_inference(self, db):
        store, repo_id = db
        gs = GraphStore()
        assert hasattr(gs, "insert_nodes")
        assert not hasattr(gs, "infer")
