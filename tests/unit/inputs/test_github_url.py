"""Tests for GitHub URL parsing and classification."""

import pytest

from fcode.inputs.errors import (
    UnsupportedRepositoryUrlError,
)
from fcode.inputs.source_classifier import (
    InputKind,
    classify,
    normalize_github_url,
    parse_github_url,
)


def test_supported_github_url_normalized():
    kind = classify("https://github.com/owner/repo")
    assert kind == InputKind.GITHUB


def test_git_suffix_accepted():
    kind = classify("https://github.com/owner/repo.git")
    assert kind == InputKind.GITHUB


def test_unsupported_host_rejected():
    with pytest.raises(UnsupportedRepositoryUrlError):
        classify("https://gitlab.com/owner/repo")


def test_malformed_github_url_rejected():
    with pytest.raises(UnsupportedRepositoryUrlError):
        classify("https://github.com/")
    with pytest.raises(UnsupportedRepositoryUrlError):
        classify("http://github.com/owner/")


def test_parse_github_url_returns_owner_repo():
    owner, repo = parse_github_url("https://github.com/my-owner/my_repo")
    assert owner == "my-owner"
    assert repo == "my_repo"


def test_parse_github_url_with_git_suffix():
    owner, repo = parse_github_url("https://github.com/owner/repo.git")
    assert owner == "owner"
    assert repo == "repo"


def test_normalize_github_url():
    result = normalize_github_url("https://github.com/owner/repo")
    assert result == "https://github.com/owner/repo.git"


def test_normalize_github_url_with_suffix():
    result = normalize_github_url("https://github.com/owner/repo.git")
    assert result == "https://github.com/owner/repo.git"


def test_empty_string_rejected():
    with pytest.raises(Exception):
        classify("")
