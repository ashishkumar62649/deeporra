"""Tests for ignore_rules.py."""

import os
import tempfile

from fcode.scanner.ignore_rules import IgnoreRules


def test_hardcoded_git_dir():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        git_path = os.path.join(tmp, ".git", "objects")
        os.makedirs(git_path, exist_ok=True)
        assert rules.is_ignored(git_path)


def test_hardcoded_fcode_dir():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        path = os.path.join(tmp, ".fcode", "index.db")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assert rules.is_ignored(path)


def test_hardcoded_node_modules():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        path = os.path.join(tmp, "node_modules", "package")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assert rules.is_ignored(path)


def test_hardcoded_pycache():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        path = os.path.join(tmp, "__pycache__", "foo.pyc")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assert rules.is_ignored(path)


def test_hardcoded_pyc():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        fpath = os.path.join(tmp, "module.pyc")
        with open(fpath, "w") as f:
            f.write("")
        assert rules.is_ignored(fpath)


def test_env_file_excluded():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        fpath = os.path.join(tmp, ".env")
        with open(fpath, "w") as f:
            f.write("KEY=val")
        assert rules.is_ignored(fpath)


def test_env_dot_file_excluded():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        fpath = os.path.join(tmp, ".env.local")
        with open(fpath, "w") as f:
            f.write("KEY=val")
        assert rules.is_ignored(fpath)


def test_is_env_file():
    assert IgnoreRules.is_env_file("/path/to/.env")
    assert IgnoreRules.is_env_file("/path/to/.env.production")
    assert not IgnoreRules.is_env_file("/path/to/app.py")


def test_gitignore_respected():
    with tempfile.TemporaryDirectory() as tmp:
        ignore_content = "build/\n*.log\n"
        with open(os.path.join(tmp, ".gitignore"), "w") as f:
            f.write(ignore_content)
        rules = IgnoreRules(tmp)
        build_dir = os.path.join(tmp, "build")
        os.makedirs(build_dir, exist_ok=True)
        assert rules.is_ignored(os.path.join(build_dir, "out.o"))
        log_path = os.path.join(tmp, "app.log")
        with open(log_path, "w") as f:
            f.write("")
        assert rules.is_ignored(log_path)
        py_path = os.path.join(tmp, "app.py")
        with open(py_path, "w") as f:
            f.write("")
        assert not rules.is_ignored(py_path)


def test_fcodeignore_supplements():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".fcodeignore"), "w") as f:
            f.write("secret/\n")
        rules = IgnoreRules(tmp)
        secret_dir = os.path.join(tmp, "secret")
        os.makedirs(secret_dir, exist_ok=True)
        assert rules.is_ignored(secret_dir)


def test_normal_file_not_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        fpath = os.path.join(tmp, "main.py")
        with open(fpath, "w") as f:
            f.write("print(1)")
        assert not rules.is_ignored(fpath)


def test_nested_ignored_dir():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        path = os.path.join(tmp, "src", "node_modules", "pkg")
        os.makedirs(path, exist_ok=True)
        assert rules.is_ignored(path)


def test_venv_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        rules = IgnoreRules(tmp)
        path = os.path.join(tmp, ".venv", "bin")
        os.makedirs(path, exist_ok=True)
        assert rules.is_ignored(path)
