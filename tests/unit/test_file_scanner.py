"""Tests for file_scanner.py."""

import os
import tempfile

from fcode.contracts.models import RepoInput
from fcode.contracts.enums import FileType
from fcode.scanner.file_scanner import scan


def _repo(tmp):
    return RepoInput(repo_path=tmp)


def test_invalid_path():
    result = scan(RepoInput(repo_path="/nonexistent_path_xyz"))
    assert result.total_count == 0


def test_empty_repository():
    with tempfile.TemporaryDirectory() as tmp:
        result = scan(_repo(tmp))
        assert result.total_count == 0


def test_python_source():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "main.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1
        assert result.files[0].file_type == FileType.PYTHON


def test_python_test_classification():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "test_main.py"), "w") as f:
            f.write("def test_x(): pass\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1
        assert result.files[0].file_type == FileType.PYTHON


def test_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "README.md"), "w") as f:
            f.write("# Title\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1
        assert result.files[0].file_type == FileType.MARKDOWN


def test_config_file():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "config.json"), "w") as f:
            f.write('{"key": "val"}\n')
        result = scan(_repo(tmp))
        assert result.total_count == 1
        assert result.files[0].file_type == FileType.CONFIG


def test_deterministic_ordering():
    with tempfile.TemporaryDirectory() as tmp:
        for fname in ["z.py", "a.py", "m.py"]:
            with open(os.path.join(tmp, fname), "w") as f:
                f.write("x = 1\n")
        result = scan(_repo(tmp))
        paths = [f.file_path for f in result.files]
        assert paths == sorted(paths, key=lambda p: (p.lower(), p))


def test_symlinked_file():
    if not hasattr(os, "symlink"):
        return
    try:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "real.py")
            with open(target, "w") as f:
                f.write("x = 1\n")
            link = os.path.join(tmp, "link.py")
            os.symlink(target, link)
            result = scan(_repo(tmp))
            assert result.total_count == 1
            assert result.files[0].file_path == "real.py"
    except OSError:
        pass


def test_symlinked_directory():
    if not hasattr(os, "symlink"):
        return
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "app.py"), "w") as f:
                f.write("x = 1\n")
            link = os.path.join(tmp, "linked")
            os.symlink(src, link)
            result = scan(_repo(tmp))
            assert result.total_count == 1
    except OSError:
        pass


def test_oversized_file():
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "big.py")
        with open(fpath, "wb") as f:
            f.write(b"x\n" * (2 * 1024 * 1024))
        with open(os.path.join(tmp, "small.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1


def test_binary_file():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "img.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1


def test_env_file_excluded():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".env"), "w") as f:
            f.write("API_KEY=secret\n")
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1


def test_secret_bearing_file():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "config.py"), "w") as f:
            f.write('API_KEY="sk_test_abcdefghijklmnopqrstuvwxyz"\n')
        result = scan(_repo(tmp))
        assert result.total_count == 1


def test_gitignore_respected():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".gitignore"), "w") as f:
            f.write("build/\n")
        os.makedirs(os.path.join(tmp, "build"), exist_ok=True)
        with open(os.path.join(tmp, "build", "out.o"), "w") as f:
            f.write("")
        with open(os.path.join(tmp, "main.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        # .gitignore and main.py are both eligible; build/out.o is ignored
        assert result.total_count == 2


def test_fcode_dir_excluded():
    with tempfile.TemporaryDirectory() as tmp:
        fcode = os.path.join(tmp, ".fcode")
        os.makedirs(fcode)
        with open(os.path.join(fcode, "config.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(tmp, "main.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1


def test_diagnostics():
    with tempfile.TemporaryDirectory() as tmp:
        bpath = os.path.join(tmp, "big.py")
        with open(bpath, "wb") as f:
            f.write(b"x\n" * (2 * 1024 * 1024))
        result = scan(_repo(tmp))
        assert result.total_count == 0
        skipped_reasons = [s.reason for s in result.skipped]
        assert any("oversized" in s for s in skipped_reasons)


def test_unreadable_file():
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "secret.txt")
        with open(fpath, "w") as f:
            f.write("data\n")
        try:
            os.chmod(fpath, 0o000)
        except OSError:
            return
        try:
            with open(os.path.join(tmp, "app.py"), "w") as f:
                f.write("x = 1\n")
            result = scan(_repo(tmp))
            # On some platforms chmod may not prevent reading
            assert result.total_count in (1, 2)
        finally:
            try:
                os.chmod(fpath, 0o644)
            except OSError:
                pass


def test_posix_relative_paths():
    with tempfile.TemporaryDirectory() as tmp:
        sub = os.path.join(tmp, "sub", "dir")
        os.makedirs(sub)
        with open(os.path.join(sub, "app.py"), "w") as f:
            f.write("x = 1\n")
        result = scan(_repo(tmp))
        assert result.total_count == 1
        assert "\\" not in result.files[0].file_path


def test_eligible_counts_and_total_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "a.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(tmp, "b.py"), "w") as f:
            f.write("y = 2\n")
        result = scan(_repo(tmp))
        assert result.total_count == 2
        assert result.total_bytes > 0
