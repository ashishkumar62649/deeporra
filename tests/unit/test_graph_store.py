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


class TestGraphStoreProtocol:
    """Public Protocol-surface tests — store_graph() and reset()."""

    def test_store_graph_writes_nodes(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        nodes = [
            {
                "id": str(uuid_mod.uuid4()),
                "repo_id": repo_id,
                "node_id": "file:main.py",
                "label": "main.py",
                "node_type": "file",
                "source_file": "main.py",
                "confidence": "EXTRACTED",
            }
        ]
        gs.store_graph(nodes, [])
        assert gs.count_nodes(store.conn, repo_id) == 1

    def test_store_graph_writes_edges(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        nid1 = str(uuid_mod.uuid4())
        nid2 = str(uuid_mod.uuid4())
        nodes = [
            {"id": nid1, "repo_id": repo_id, "node_id": "file:a.py", "label": "a.py",
             "node_type": "file", "source_file": "a.py", "confidence": "EXTRACTED"},
            {"id": nid2, "repo_id": repo_id, "node_id": "import:os", "label": "os",
             "node_type": "import", "source_file": "a.py", "confidence": "EXTRACTED"},
        ]
        edges = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "source_node_id": "file:a.py", "target_node_id": "import:os",
             "relation": "imports", "confidence": "EXTRACTED", "source_file": "a.py"},
        ]
        gs.store_graph(nodes, edges)
        assert gs.count_edges(store.conn, repo_id) == 1

    def test_supplied_node_uuid_preserved(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        my_uuid = str(uuid_mod.uuid4())
        nodes = [
            {"id": my_uuid, "repo_id": repo_id, "node_id": "file:u.py", "label": "u.py",
             "node_type": "file", "source_file": "u.py", "confidence": "EXTRACTED"},
        ]
        gs.store_graph(nodes, [])
        rows = gs.get_nodes(store.conn, repo_id)
        assert any(r["id"] == my_uuid for r in rows)

    def test_supplied_edge_uuid_preserved(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        nid1 = str(uuid_mod.uuid4())
        nid2 = str(uuid_mod.uuid4())
        edge_uuid = str(uuid_mod.uuid4())
        nodes = [
            {"id": nid1, "repo_id": repo_id, "node_id": "file:x.py", "label": "x.py",
             "node_type": "file", "source_file": "x.py", "confidence": "EXTRACTED"},
            {"id": nid2, "repo_id": repo_id, "node_id": "import:sys", "label": "sys",
             "node_type": "import", "source_file": "x.py", "confidence": "EXTRACTED"},
        ]
        edges = [
            {"id": edge_uuid, "repo_id": repo_id,
             "source_node_id": "file:x.py", "target_node_id": "import:sys",
             "relation": "imports", "confidence": "EXTRACTED", "source_file": "x.py"},
        ]
        gs.store_graph(nodes, edges)
        rows = gs.get_edges(store.conn, repo_id)
        assert any(r["id"] == edge_uuid for r in rows)

    def test_enum_values_persist_as_value(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        nodes = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "node_id": "func:bar", "label": "bar", "node_type": "function",
             "source_file": "b.py", "confidence": "AMBIGUOUS"},
        ]
        edges = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "source_node_id": "func:bar", "target_node_id": "func:baz",
             "relation": "calls", "confidence": "INFERRED", "source_file": "b.py"},
        ]
        gs.store_graph(nodes, edges)
        rows = gs.get_nodes(store.conn, repo_id)
        assert rows[0]["node_type"] == "function"
        assert rows[0]["confidence"] == "AMBIGUOUS"
        erows = gs.get_edges(store.conn, repo_id)
        assert erows[0]["relation"] == "calls"
        assert erows[0]["confidence"] == "INFERRED"

    def test_multiple_edges_different_evidence_preserved(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        nid1 = str(uuid_mod.uuid4())
        nid2 = str(uuid_mod.uuid4())
        nodes = [
            {"id": nid1, "repo_id": repo_id, "node_id": "file:a.py", "label": "a.py",
             "node_type": "file", "source_file": "a.py", "confidence": "EXTRACTED"},
            {"id": nid2, "repo_id": repo_id, "node_id": "import:os", "label": "os",
             "node_type": "import", "source_file": "a.py", "confidence": "EXTRACTED"},
        ]
        edges = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "source_node_id": "file:a.py", "target_node_id": "import:os",
             "relation": "imports", "confidence": "EXTRACTED", "source_file": "a.py",
             "metadata": '{"line": 1}'},
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "source_node_id": "file:a.py", "target_node_id": "import:os",
             "relation": "imports", "confidence": "EXTRACTED", "source_file": "b.py",
             "metadata": '{"line": 5}'},
        ]
        gs.store_graph(nodes, edges)
        assert gs.count_edges(store.conn, repo_id) == 2

    def test_repo_a_not_affected_by_repo_b(self, db):
        store, repo_id_a = db
        repo_id_b = store.create_repository_and_status("/tmp/repo_b")
        gs = GraphStore(conn=store.conn)
        nodes_a = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id_a,
             "node_id": "file:only_a.py", "label": "only_a.py",
             "node_type": "file", "source_file": "only_a.py", "confidence": "EXTRACTED"},
        ]
        nodes_b = [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id_b,
             "node_id": "file:only_b.py", "label": "only_b.py",
             "node_type": "file", "source_file": "only_b.py", "confidence": "EXTRACTED"},
        ]
        gs.store_graph(nodes_a, [])
        gs.store_graph(nodes_b, [])
        assert gs.count_nodes(store.conn, repo_id_a) == 1
        assert gs.count_nodes(store.conn, repo_id_b) == 1

    def test_reset_removes_all_graph_rows(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        gs.insert_nodes(store.conn, repo_id, [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "node_id": "file:r.py", "label": "r.py",
             "node_type": "file", "source_file": "r.py", "confidence": "EXTRACTED"},
        ])
        gs.reset()
        assert gs.count_nodes(store.conn, repo_id) == 0

    def test_reset_not_noop(self, db):
        store, repo_id = db
        gs = GraphStore(conn=store.conn)
        gs.insert_nodes(store.conn, repo_id, [
            {"id": str(uuid_mod.uuid4()), "repo_id": repo_id,
             "node_id": "file:n.py", "label": "n.py",
             "node_type": "file", "source_file": "n.py", "confidence": "EXTRACTED"},
        ])
        before = gs.count_nodes(store.conn, repo_id)
        gs.reset()
        after = gs.count_nodes(store.conn, repo_id)
        assert before > 0
        assert after == 0

    def test_protocol_conformance(self, db):
        import inspect
        from fcode.contracts.interfaces import GraphStoreProtocol
        sig_store = inspect.signature(GraphStoreProtocol.store_graph)
        sig_reset = inspect.signature(GraphStoreProtocol.reset)
        self_sig_store = inspect.signature(GraphStore.store_graph)
        self_sig_reset = inspect.signature(GraphStore.reset)
        assert list(sig_store.parameters.keys()) == ["self", "nodes", "edges"]
        assert list(sig_reset.parameters.keys()) == ["self"]
        assert callable(getattr(GraphStore, "store_graph"))
        assert callable(getattr(GraphStore, "reset"))
        gs = GraphStore()
        assert callable(gs.store_graph)
        assert callable(gs.reset)


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
