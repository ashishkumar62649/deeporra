"""Ignore rules — gitignore, fcodeignore, and hardcoded ignores."""

import os
import fnmatch


HARDCODED_IGNORED_DIRS = frozenset({
    ".git", ".fcode", "node_modules", "__pycache__", ".venv", "venv",
})

HARDCODED_IGNORED_FILES = frozenset({".env"})

HARDCODED_IGNORED_PATTERNS = frozenset({".env.*", "*.pyc", "*.pyo"})

IGNORE_FILE_NAMES = (".gitignore", ".fcodeignore")


class IgnoreRules:
    def __init__(self, repo_root: str):
        self._repo_root = os.path.abspath(repo_root)
        self._gitignore_patterns: list[tuple[str, list[str]]] = []
        self._fcodeignore_patterns: list[str] = []
        self._load_ignore_files()

    def _load_ignore_files(self):
        for fname in IGNORE_FILE_NAMES:
            path = os.path.join(self._repo_root, fname)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        patterns = [
                            line.strip()
                            for line in f
                            if line.strip() and not line.strip().startswith("#")
                        ]
                    if fname == ".fcodeignore":
                        self._fcodeignore_patterns = patterns
                    else:
                        self._gitignore_patterns.append((self._repo_root, patterns))
                except OSError:
                    pass

    def _rel(self, path: str) -> str:
        return os.path.relpath(path, self._repo_root).replace("\\", "/")

    def is_ignored(self, path: str) -> bool:
        norm = os.path.normpath(path)
        rel = self._rel(norm)
        name = os.path.basename(norm)

        if name in HARDCODED_IGNORED_FILES:
            return True
        if name in HARDCODED_IGNORED_DIRS:
            return True

        if any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in HARDCODED_IGNORED_PATTERNS):
            return True

        segments = rel.split("/")
        for segment in segments:
            if segment in HARDCODED_IGNORED_DIRS:
                return True

        for pattern in self._fcodeignore_patterns:
            if self._match(pattern, rel):
                return True

        for _dir_path, patterns in self._gitignore_patterns:
            for pattern in patterns:
                if self._match(pattern, rel):
                    return True

        return False

    @staticmethod
    def _match(pattern: str, rel_path: str) -> bool:
        if pattern.startswith("/"):
            return fnmatch.fnmatch(rel_path, pattern.lstrip("/"))
        if pattern.endswith("/"):
            if any(part == pattern.rstrip("/") for part in rel_path.split("/")):
                return True
            return fnmatch.fnmatch(rel_path, pattern)
        if "/" in pattern.rstrip("/"):
            return fnmatch.fnmatch(rel_path, pattern)
        return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, f"**/{pattern}")

    @staticmethod
    def is_env_file(path: str) -> bool:
        name = os.path.basename(path)
        if name == ".env":
            return True
        if name.startswith(".env."):
            return True
        return False
