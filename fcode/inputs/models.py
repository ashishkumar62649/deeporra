"""Data models for repository input preparation."""

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


class InputKind(enum.Enum):
    LOCAL = "local"
    ZIP = "zip"
    GITHUB = "github"


@dataclass
class PreparedRepository:
    input_kind: InputKind
    original_source: str
    repository_root: Path
    owns_workspace: bool
    resolved_commit: Optional[str] = None
    cleanup: Optional[Callable[[], None]] = None
    warnings: list[str] = field(default_factory=list)
    display_name: str = ""
