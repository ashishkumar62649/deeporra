"""Prepare a local folder as a validated repository directory."""

from pathlib import Path

from fcode.inputs.errors import (
    InvalidRepositorySourceError,
    RepositorySourceNotFoundError,
)
from fcode.inputs.models import InputKind, PreparedRepository


def prepare_local(source: str) -> PreparedRepository:
    raw = Path(source)

    if not raw.exists():
        raise RepositorySourceNotFoundError(f"Path does not exist: {source}")

    resolved = raw.resolve(strict=True)

    if not resolved.is_dir():
        raise InvalidRepositorySourceError(
            f"Path is not a directory: {source}"
        )

    if not _is_readable(resolved):
        raise InvalidRepositorySourceError(
            f"Directory is not readable: {source}"
        )

    display = _safe_display_name(resolved)

    return PreparedRepository(
        input_kind=InputKind.LOCAL,
        original_source=str(raw),
        repository_root=resolved,
        owns_workspace=False,
        display_name=display,
    )


def _is_readable(path: Path) -> bool:
    try:
        return any(path.iterdir()) or True
    except (PermissionError, OSError):
        return False


def _safe_display_name(path: Path) -> str:
    return path.name
