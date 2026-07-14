# DeepOrra v0.1.0 Release Checklist

## Instructions

Run every checkbox in order. Tick only after the command exits successfully
and you have verified the result manually. If a step fails, stop, fix the
root cause, and restart from the beginning of the affected section.

---

## 1. Repository Cleanliness

- [ ] `git status` reports a clean working tree (no modified, staged, or
      untracked files in tracked paths; generated artifacts in `.gitignore`
      are allowed)
- [ ] `git log --oneline --first-parent` shows a linear, reviewed history
      with no WIP or temporary commits
- [ ] The release commit is the exact `HEAD` of `main`. Record the full SHA:
      `RELEASE_SHA=$(git rev-parse HEAD)`

## 2. Version and Metadata

- [ ] `pyproject.toml` contains `version = "0.1.0"`
- [ ] `pyproject.toml` contains `name = "deeporra"` with no typos
- [ ] `pyproject.toml` contains `requires-python = ">=3.10"`
- [ ] `deeporra/__init__.py` (or `__version__`) matches `0.1.0`

## 3. README, LICENSE, SECURITY, CHANGELOG

- [ ] `README.md` exists, renders correctly, and contains no placeholder
      or TODO text
- [ ] `LICENSE` exists and contains the MIT license text
- [ ] `SECURITY.md` exists and is accurate for the public release
- [ ] `CHANGELOG.md` exists at the repository root and documents the
      v0.1.0 release with notable changes, credits, and upgrade notes
- [ ] The changelog does not expose any unpatched vulnerability details

## 4. Complete Test Suite

- [ ] `python -m pytest tests/ -v --tb=short` passes with **zero failures**
      and **zero skipped** tests
- [ ] Review output: all expected test files ran, no modules were silently
      omitted due to missing dependencies
- [ ] `python -m pytest tests/ --cov=deeporra --cov-report=term-missing`
      runs without error (coverage target is advisory, not blocking)

## 5. Doctor Checks

- [ ] `python -m deeporra doctor <repo>` completes with exit code 0 and
      reports all health checks passing
- [ ] Test with a nonexistent path: `python -m deeporra doctor
      /nonexistent/path` exits with a non-zero exit code and an appropriate
      error message

## 6. MCP Tools — All Eight

- [ ] Start the MCP server in one terminal:
      `python -m deeporra.mcp_server`
- [ ] Send each of the eight tool requests and confirm a valid non-error
      JSON response:
      - `repository_summary`
      - `search_code`
      - `hybrid_search`
      - `find_symbols`
      - `find_routes`
      - `get_related_code`
      - `analyze_change_impact`
      - `find_existing_implementation`

## 7. Dashboard Smoke Test

- [ ] Start the dashboard: `python -m deeporra.dashboard`
- [ ] Confirm that `http://localhost:8501` is reachable and renders the
      main page without JavaScript errors
- [ ] Confirm the sidebar displays "Local-only · Read-only · Secrets are
      detected and redacted."

## 8. Wheel and SDist Build

- [ ] `python -m build` produces exactly two files in `dist/`:
      - `deeporra-0.1.0-py3-none-any.whl`
      - `deeporra-0.1.0.tar.gz`
- [ ] No stale artifacts from previous builds exist in `dist/`

## 9. Artifact Inspection and SHA-256

- [ ] `unzip -l dist/deeporra-0.1.0-py3-none-any.whl` lists expected
      package files only (no `tests/`, no `.venv/`, no raw `deeporra/`
      source outside the installed layout)
- [ ] `tar --list -f dist/deeporra-0.1.0.tar.gz` confirms the sdist
      includes `pyproject.toml`, `README.md`, `LICENSE`, `SECURITY.md`,
      and `deeporra/` package tree
- [ ] Record SHA-256 checksums (do not embed in this file):
      ```
      sha256sum dist/deeporra-0.1.0-py3-none-any.whl
      sha256sum dist/deeporra-0.1.0.tar.gz
      ```

## 10. Fresh Pip Installation

- [ ] Create a clean virtual environment:
      `python -m venv /tmp/deeporra-test-pip`
- [ ] Activate and install: `pip install dist/deeporra-0.1.0-py3-none-any.whl`
- [ ] Run `python -m deeporra doctor <repo>` to confirm the package is
      importable and the CLI works

## 11. Fresh UV Tool Installation

- [ ] Install uv if not available: `pip install uv` or system package manager
- [ ] Register the wheel as a uv tool:
      `uv tool install dist/deeporra-0.1.0-py3-none-any.whl`
- [ ] Run `deeporra doctor <repo>` to confirm the tool works

## 12. UVX Verification

- [ ] Run `uvx deeporra doctor <repo>` from a directory that is NOT the
      repository root to confirm the tool resolves and works via `uvx`
- [ ] Confirm exit code 0 and valid output

## 13. TestPyPI Upload and Clean Installation

- [ ] Upload to TestPyPI:
      ```
      twine upload --repository-url https://test.pypi.org/legacy/ dist/*
      ```
- [ ] Create a clean virtual environment
- [ ] Install from TestPyPI:
      ```
      pip install --index-url https://test.pypi.org/simple/ deeporra==0.1.0
      ```
- [ ] Confirm `deeporra doctor <repo>` works from the TestPyPI install
- [ ] If the TestPyPI release is defective or misleading, yank it:
      `twine yank deeporra==0.1.0 --repository-url https://test.pypi.org/legacy/`

## 14. GitHub Actions and Trusted Publishing

- [ ] Confirm the PyPI publishing workflow exists in
      `.github/workflows/publish.yml` (or equivalent)
- [ ] Confirm Trusted Publishing is configured (OIDC-based, no stored
      PyPI token)
- [ ] Confirm the workflow is triggered only by the `v0.1.0` tag push

## 15. v0.1.0 Tag

- [ ] Create and push the tag:
      ```
      git tag -a v0.1.0 -m "DeepOrra v0.1.0"
      git push origin v0.1.0
      ```
- [ ] Confirm the tag points at the recorded `RELEASE_SHA`
- [ ] Monitor the GitHub Actions publishing workflow for success

## 16. Production PyPI Publication

- [ ] Confirm the wheel and sdist appear on
      `https://pypi.org/project/deeporra/0.1.0/`
- [ ] Confirm the version is `0.1.0` and the publish timestamp is correct
- [ ] Confirm metadata (license, Python version, description) is accurate

## 17. GitHub Release and Attached Artifacts

- [ ] Draft a new GitHub Release:
      - Tag: `v0.1.0`
      - Title: `DeepOrra v0.1.0`
      - Body: link to changelog, highlight key features and known limitations
- [ ] Attach `deeporra-0.1.0-py3-none-any.whl` and
      `deeporra-0.1.0.tar.gz` to the release
- [ ] Publish the release

## 18. Post-Release Pip and UV Verification

- [ ] Create a clean virtual environment and run:
      `pip install deeporra==0.1.0`
- [ ] Confirm `deeporra doctor <repo>` works
- [ ] In a different environment, run:
      `uv tool install deeporra==0.1.0`
- [ ] Confirm `deeporra doctor <repo>` works
- [ ] Run `uvx deeporra==0.1.0 doctor <repo>` and confirm it works

## 19. Rollback, Yanking, and Incident Notes

- [ ] If the release is broken, yank from PyPI:
      `twine yank deeporra==0.1.0`
- [ ] If a yank is issued, update the GitHub Release to note the yank
      and the reason
- [ ] Record any post-release issues in the changelog and an incident
      note in `docs/` for future reference

---

## Reference

- PyPI project: https://pypi.org/project/deeporra/
- GitHub repo: https://github.com/ashishkumar62649/deeporra
- Documentation: `docs/01_CONTEXT.md` through `docs/09_AGENT_TASKS.md`
