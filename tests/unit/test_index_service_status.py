"""Active-generation status reads without indexing work."""

import json

import pytest

from fcode.contracts import IndexCounts, IndexState
from fcode.indexing import ActiveStatusReader, IndexService
from fcode.storage.sqlite_store import SQLiteStore


def _active_status_repo(tmp_path):
    generation = "generation-status"
    root = tmp_path / ".fcode" / "generations" / generation
    root.mkdir(parents=True)
    (tmp_path / ".fcode" / "active.json").write_text(json.dumps({"generation": generation}), encoding="utf-8")
    store = SQLiteStore(str(root / "index.db"))
    store.connect()
    store.initialize_schema()
    repo_id = store.create_repository_and_status(str(tmp_path))
    store.update_index_status(repo_id, status="complete", total_files=3, indexed_files=2, total_chunks=4, total_vectors=1, total_graph_nodes=5, total_edges=6)
    store.commit_transaction()
    store.close()


def test_status_reader_reads_active_snapshot_without_creating_workspace(tmp_path):
    _active_status_repo(tmp_path)
    status = ActiveStatusReader(str(tmp_path)).read()
    assert status.state == IndexState.COMPLETE
    assert status.counts.scanned == 3
    assert status.counts.chunks == 4
    assert status.counts.graph_nodes == 5


def test_status_methods_require_an_injected_reader_before_io():
    service = IndexService(object(), object(), object())
    with pytest.raises(TypeError, match="status_reader"):
        service.get_status()


def test_status_methods_delegate_to_one_reader_snapshot():
    class Reader:
        def __init__(self): self.calls = 0
        def read(self):
            self.calls += 1
            from fcode.contracts import IndexStatusRecord
            return IndexStatusRecord(state=IndexState.COMPLETE, counts=IndexCounts(chunks=7))
    reader = Reader()
    service = IndexService(object(), object(), object(), status_reader=reader)
    assert service.get_status().counts.chunks == 7
    assert service.get_counts().chunks == 7
    assert reader.calls == 2
