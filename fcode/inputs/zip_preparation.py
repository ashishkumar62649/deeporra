"""Prepare a ZIP archive — extract safely into an owned workspace."""

import os
import zipfile
from pathlib import Path

from fcode.inputs.errors import (
    ArchiveLimitExceededError,
    RepositorySourceNotFoundError,
    UnsafeArchiveError,
)
from fcode.inputs.models import InputKind, PreparedRepository
from fcode.inputs.workspace import OwnedWorkspace

_MAX_FILES = 10_000
_MAX_TOTAL_BYTES = 524_288_000
_MAX_FILE_SIZE = 104_857_600
_MAX_COMPRESSION_RATIO = 100


def prepare_zip(source: str, workspace_root: Path) -> PreparedRepository:
    zip_path = Path(source)

    if not zip_path.is_file():
        raise RepositorySourceNotFoundError(f"ZIP file not found: {source}")

    if zip_path.suffix.lower() != ".zip":
        raise RepositorySourceNotFoundError(f"Not a ZIP file: {source}")

    workspace = OwnedWorkspace(workspace_root)
    extraction_root = workspace.root

    try:
        _safe_extract(zip_path, extraction_root)
    except Exception:
        workspace.cleanup()
        raise

    repo_root = _detect_root(extraction_root)

    display = zip_path.stem

    def cleanup():
        workspace.cleanup()

    return PreparedRepository(
        input_kind=InputKind.ZIP,
        original_source=str(zip_path.resolve()),
        repository_root=repo_root,
        owns_workspace=True,
        cleanup=cleanup,
        display_name=display,
    )


def _safe_extract(zip_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), "r") as zf:
        _validate_infos(zf, target)

        file_count = 0
        total_bytes = 0

        for info in zf.infolist():
            if info.filename.endswith("/"):
                (target / info.filename).mkdir(parents=True, exist_ok=True)
                continue

            file_count += 1
            if file_count > _MAX_FILES:
                raise ArchiveLimitExceededError(
                    f"ZIP contains more than {_MAX_FILES} files."
                )

            dest = (target / info.filename).resolve()
            if not str(dest).startswith(str(target.resolve())):
                raise UnsafeArchiveError(
                    f"Archive entry escapes extraction root: {info.filename}"
                )

            if info.file_size > _MAX_FILE_SIZE:
                raise ArchiveLimitExceededError(
                    f"File exceeds maximum size: {info.filename} "
                    f"({info.file_size} > {_MAX_FILE_SIZE})"
                )

            total_bytes += info.file_size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ArchiveLimitExceededError(
                    f"Total uncompressed size exceeds {_MAX_TOTAL_BYTES} bytes."
                )

            cratio = info.compress_size / info.file_size if info.file_size > 0 else 0
            if cratio > 0 and 1 / cratio > _MAX_COMPRESSION_RATIO:
                raise ArchiveLimitExceededError(
                    f"Compression ratio exceeds limit for: {info.filename}"
                )

            dest.parent.mkdir(parents=True, exist_ok=True)
            zf.extract(info, str(target))


def _validate_infos(zf: zipfile.ZipFile, target: Path) -> None:
    seen_dirs: set[str] = set()
    seen_files: set[str] = set()
    target_str = str(target.resolve())

    for info in zf.infolist():
        raw = info.filename
        norm = os.path.normpath(raw).replace("\\", "/")

        if raw.startswith("/"):
            raise UnsafeArchiveError(f"Absolute path in archive: {raw}")

        if raw.startswith(("\\", "\\\\")):
            raise UnsafeArchiveError(f"Windows drive path in archive: {raw}")

        if len(raw) >= 2 and raw[1] == ":":
            raise UnsafeArchiveError(f"Windows drive path in archive: {raw}")

        if norm.startswith("..") or "/.." in norm:
            raise UnsafeArchiveError(f"Path traversal in archive: {raw}")

        full = str((target / norm).resolve())
        if not full.startswith(target_str):
            raise UnsafeArchiveError(f"Entry escapes after normalization: {raw}")

        if raw.endswith("/"):
            if norm in seen_dirs:
                raise UnsafeArchiveError(f"Duplicate directory entry: {raw}")
            if norm in seen_files:
                raise UnsafeArchiveError(f"Directory collides with file: {raw}")
            seen_dirs.add(norm)
        else:
            if norm in seen_files:
                raise UnsafeArchiveError(f"Duplicate file entry: {raw}")
            if norm in seen_dirs:
                raise UnsafeArchiveError(f"File collides with directory: {raw}")
            seen_files.add(norm)

        if _is_special(info):
            raise UnsafeArchiveError(f"Unsafe entry type in archive: {raw}")

        _check_unsafe_symlink_target(info)


def _is_special(info: zipfile.ZipInfo) -> bool:
    external_attr = info.external_attr >> 16
    if external_attr & 0o120000:
        return True
    return False


def _check_unsafe_symlink_target(info: zipfile.ZipInfo) -> None:
    if info.create_system == 3 and info.filename.startswith(".."):
        raise UnsafeArchiveError(f"Symlink traversal in archive: {info.filename}")


def _detect_root(extraction_root: Path) -> Path:
    entries = list(extraction_root.iterdir())

    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file() and not _is_metadata(e)]

    if len(dirs) == 1 and not files:
        return dirs[0]

    return extraction_root


def _is_metadata(path: Path) -> bool:
    name = path.name
    if name in ("__MACOSX", ".DS_Store", "Thumbs.db"):
        return True
    if name.startswith("._"):
        return True
    return False
