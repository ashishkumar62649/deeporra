"""Read one immutable snapshot from the active complete generation."""

from fcode.contracts import IndexCounts, IndexPhase, IndexState, IndexStatusRecord
from fcode.indexing.full_rebuild import FullRebuildCoordinator, FullRebuildError
from fcode.storage.sqlite_store import SQLiteStore


class ActiveStatusReader:
    def __init__(self, repo_path: str) -> None:
        self._coordinator = FullRebuildCoordinator(repo_path)

    def read(self) -> IndexStatusRecord:
        generation = self._coordinator.active_generation()
        if generation is None:
            return IndexStatusRecord(state=IndexState.PENDING, message="No active index.")
        store = SQLiteStore(str(self._coordinator.workspace / "generations" / generation / "index.db"))
        try:
            store.connect()
            repo_id = store.find_repository(str(self._coordinator.workspace.parent))
            row = store.read_index_status(repo_id) if repo_id else None
        finally:
            store.close()
        if row is None or row["status"] != IndexState.COMPLETE.value:
            raise FullRebuildError("active index status is unavailable")
        counts = IndexCounts(
            scanned=row["total_files"] or 0,
            parsed=row["indexed_files"] or 0,
            symbols=row["total_symbols"] or 0,
            chunks=row["total_chunks"] or 0,
            embedded=row["total_vectors"] or 0,
            graph_nodes=row["total_graph_nodes"] or 0,
            graph_edges=row["total_edges"] or 0,
            warnings=row["warning_count"] or 0,
            errors=row["error_count"] or 0,
        )
        return IndexStatusRecord(
            state=IndexState.COMPLETE,
            phase=IndexPhase.PERSIST,
            completed_phase=IndexPhase.PERSIST,
            counts=counts,
            total_vectors=counts.embedded,
            error_count=counts.errors,
        )
