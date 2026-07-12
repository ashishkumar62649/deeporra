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
        count_fields = IndexCounts.__dataclass_fields__
        if any(f"count_{field}" not in row or row[f"count_{field}"] is None for field in count_fields):
            raise FullRebuildError("active index status is unavailable")
        counts = IndexCounts(**{field: row[f"count_{field}"] for field in count_fields})
        return IndexStatusRecord(
            state=IndexState.COMPLETE,
            phase=IndexPhase.PERSIST,
            completed_phase=IndexPhase.PERSIST,
            counts=counts,
            total_vectors=counts.embedded,
            error_count=counts.errors,
        )
