"""Owned workspace lifecycle — temporary directories with safe cleanup."""

import shutil
import tempfile
from pathlib import Path

from deeporra.inputs.errors import WorkspaceCleanupError

_DEEPORRA_PROJECT_MARKERS = frozenset({".deeporra", ".git", "DeepOrra", "AGENTS.md"})


class OwnedWorkspace:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(tempfile.mkdtemp(prefix="DEEPORRA_"))
            self._cleanup_root = root
        else:
            root.mkdir(parents=True, exist_ok=True)
            self._cleanup_root = root
        self._root = root
        self._cleaned = False
        self._context_entered = False

    @property
    def root(self) -> Path:
        return self._root

    def cleanup(self) -> None:
        if self._cleaned:
            return

        self._validate_cleanup_safety(self._root)

        try:
            shutil.rmtree(self._root, ignore_errors=False)
            self._cleaned = True
        except OSError as e:
            raise WorkspaceCleanupError(
                f"Failed to clean workspace: {e}"
            )

    def __enter__(self):
        self._context_entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._cleaned:
            self.cleanup()

    @staticmethod
    def _validate_cleanup_safety(path: Path) -> None:
        resolved = path.resolve()

        if resolved.parent == resolved:
            raise WorkspaceCleanupError("Refusing to clean a drive root.")

        if _is_DEEPORRA_project_root(resolved):
            raise WorkspaceCleanupError(
                "Refusing to clean the DeepOrra project directory."
            )

    def __repr__(self) -> str:
        return f"OwnedWorkspace(root={self._root}, cleaned={self._cleaned})"


def _is_DEEPORRA_project_root(path: Path) -> bool:
    try:
        entries = set(p.name for p in path.iterdir())
        return bool(entries & _DEEPORRA_PROJECT_MARKERS)
    except (PermissionError, OSError):
        return False
