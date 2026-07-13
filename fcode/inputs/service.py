"""Unified entry point for repository input preparation."""

import tempfile
from pathlib import Path
from typing import Optional

from fcode.inputs.errors import (
    InvalidRepositorySourceError,
    RepositoryInputError,
    RepositorySourceNotFoundError,
)
from fcode.inputs.github_preparation import prepare_github
from fcode.inputs.local_preparation import prepare_local
from fcode.inputs.models import InputKind, PreparedRepository
from fcode.inputs.source_classifier import classify
from fcode.inputs.zip_preparation import prepare_zip


class RepositoryInputService:
    def prepare(
        self,
        source: str | Path,
        *,
        ref: Optional[str] = None,
        workspace_root: Optional[Path] = None,
    ) -> PreparedRepository:
        source_str = str(source)

        kind = classify(source_str)

        if kind == InputKind.LOCAL:
            return prepare_local(source_str)

        if kind == InputKind.ZIP:
            ws = workspace_root or Path(
                tempfile.mkdtemp(prefix="fcode_zip_")
            )
            return prepare_zip(source_str, ws)

        if kind == InputKind.GITHUB:
            ws = workspace_root or Path(
                tempfile.mkdtemp(prefix="fcode_gh_")
            )
            return prepare_github(source_str, ref=ref, workspace_root=ws)

        raise InvalidRepositorySourceError(
            f"Unrecognised source type: {source_str[:200]}"
        )
