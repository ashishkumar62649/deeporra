"""Unified entry point for repository input preparation."""

import tempfile
from pathlib import Path
from typing import Optional

from deeporra.inputs.errors import InvalidRepositorySourceError
from deeporra.inputs.github_preparation import prepare_github
from deeporra.inputs.local_preparation import prepare_local
from deeporra.inputs.models import InputKind, PreparedRepository
from deeporra.inputs.source_classifier import classify
from deeporra.inputs.zip_preparation import prepare_zip


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
                tempfile.mkdtemp(prefix="DEEPORRA_zip_")
            )
            return prepare_zip(source_str, ws)

        if kind == InputKind.GITHUB:
            ws = workspace_root or Path(
                tempfile.mkdtemp(prefix="DEEPORRA_gh_")
            )
            return prepare_github(source_str, ref=ref, workspace_root=ws)

        raise InvalidRepositorySourceError(
            f"Unrecognised source type: {source_str[:200]}"
        )
