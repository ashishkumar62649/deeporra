"""Prepare a GitHub repository — clone into an owned workspace via subprocess."""

import os
import re
import subprocess
import sys
from pathlib import Path

from fcode.inputs.errors import (
    GitCloneError,
    GitUnavailableError,
    RepositorySourceNotFoundError,
    UnsupportedRepositoryUrlError,
)
from fcode.inputs.models import InputKind, PreparedRepository
from fcode.inputs.source_classifier import normalize_github_url, parse_github_url
from fcode.inputs.workspace import OwnedWorkspace

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

_CLONE_TIMEOUT = 300


def prepare_github(
    url: str,
    *,
    ref: str | None = None,
    workspace_root: Path,
) -> PreparedRepository:
    _ensure_git_available()

    if not url.startswith("https://github.com/"):
        raise UnsupportedRepositoryUrlError(
            f"Only HTTPS GitHub URLs are supported: {url}"
        )

    owner, _ = parse_github_url(url)
    clone_url = normalize_github_url(url)

    workspace = OwnedWorkspace(workspace_root)
    clone_dir = workspace.root / "repo"

    try:
        clone_dir.mkdir(parents=True, exist_ok=True)
        _clone(clone_url, clone_dir, ref)

        resolved_commit = _rev_parse_head(clone_dir)

        display = f"{owner}/{clone_dir.name}"

        def cleanup():
            workspace.cleanup()

        return PreparedRepository(
            input_kind=InputKind.GITHUB,
            original_source=url,
            repository_root=clone_dir,
            owns_workspace=True,
            resolved_commit=resolved_commit,
            cleanup=cleanup,
            display_name=display,
        )

    except GitCloneError:
        workspace.cleanup()
        raise
    except Exception as exc:
        workspace.cleanup()
        raise GitCloneError(
            f"Failed to prepare repository from URL: {url}"
        ) from exc


def _ensure_git_available() -> None:
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise GitUnavailableError(
            "Git executable not found. Install Git to clone repositories."
        )


def _clone(clone_url: str, target: Path, ref: str | None) -> None:
    if ref and _COMMIT_SHA_RE.match(ref):
        _clone_and_checkout_commit(clone_url, target, ref)
    elif ref:
        _clone_branch_or_tag(clone_url, target, ref)
    else:
        _clone_default(clone_url, target)


def _clone_default(clone_url: str, target: Path) -> None:
    _run_git(
        ["clone", "--config", "core.hooksPath=/dev/null", clone_url, str(target)],
    )


def _clone_branch_or_tag(clone_url: str, target: Path, ref: str) -> None:
    _run_git(
        [
            "clone", "--config", "core.hooksPath=/dev/null",
            "--depth", "1",
            "--branch", ref,
            clone_url,
            str(target),
        ],
    )


def _clone_and_checkout_commit(clone_url: str, target: Path, commit: str) -> None:
    _run_git(
        ["clone", "--config", "core.hooksPath=/dev/null", clone_url, str(target)],
    )
    _run_git(["checkout", commit], cwd=target)


def _rev_parse_head(repo_path: Path) -> str:
    result = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
    return result.strip()


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    cmd = ["git"] + args
    env = _git_env()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CLONE_TIMEOUT,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
    except FileNotFoundError:
        raise GitUnavailableError("Git executable not found.")
    except subprocess.TimeoutExpired:
        raise GitCloneError("Git operation timed out.")

    if result.returncode != 0:
        _raise_clone_error(cmd, result)

    return result.stdout


def _raise_clone_error(cmd: list[str], result: subprocess.CompletedProcess) -> None:
    stderr = result.stderr.strip() if result.stderr else ""
    sanitized = _sanitize_stderr(stderr)
    msg = f"Git command failed: {sanitized}" if sanitized else "Git command failed."
    raise GitCloneError(msg)


def _sanitize_stderr(stderr: str) -> str:
    if not stderr:
        return ""
    safe = stderr[:500]
    safe = safe.replace("\\n", " ").replace("\\r", "")
    safe = _strip_url_credentials(safe)
    for prefix in ("fatal: ", "error: ", "warning: "):
        if safe.startswith(prefix):
            safe = safe[len(prefix):]
    safe = safe.strip()[:200]
    return safe


def _strip_url_credentials(text: str) -> str:
    import re
    return re.sub(r"://[^@/]+@", "://<credentials>@", text)


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    env.pop("GIT_INDEX_FILE", None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env
