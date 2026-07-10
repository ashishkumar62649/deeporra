"""Tests for file_scanner.py."""

import os
import tempfile
from fcode.contracts import FCodeConfig, FileType, ParseStatus, RepoInput
from fcode.scanner.file_scanner import scan


def _repo(tmpdir: str) -> RepoInput:
    return RepoInput(repo_path=tmpdir)


def _config(tmpdir: str) -> FCodeConfig:
    return FCodeConfig(repo_path=tmpdir)


def test_scan_returns_scanresult():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert hasattr(result, "files")
        assert hasattr(result, "skipped")


def test_scan_python_file():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "hello.py"), "w") as f:
            f.write("print('hello')\n")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) == 1
        assert result.files[0].file_path == "hello.py"
        assert result.files[0].language == "Python"


def test_scan_empty_directory():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files == []


def test_scan_non_python_included():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "data.txt"), "w") as f:
            f.write("hello")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) >= 1
        assert result.files[0].file_path == "data.txt"
        assert result.files[0].language is None


def test_scan_nested_file():
    with tempfile.TemporaryDirectory() as tmp:
        sub = os.path.join(tmp, "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "mod.py"), "w") as f:
            f.write("# ok")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) == 1
        assert result.files[0].file_path == "sub/mod.py"


def test_scan_file_id_format():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files[0].file_id.startswith("file:")


def test_scan_file_id_unique():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "a"))
        os.makedirs(os.path.join(tmp, "b"))
        with open(os.path.join(tmp, "a", "mod.py"), "w") as f:
            f.write("x=1")
        with open(os.path.join(tmp, "b", "mod.py"), "w") as f:
            f.write("y=2")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) == 2
        assert result.files[0].file_id != result.files[1].file_id


def test_scan_deterministic_ordering():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "z.py"), "w") as f:
            f.write("z")
        with open(os.path.join(tmp, "a.py"), "w") as f:
            f.write("a")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        names = [os.path.basename(f.file_path) for f in result.files]
        assert names == sorted(names)


def test_scan_absolute_path():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        for sf in result.files:
            assert os.path.isabs(sf.absolute_path)


def test_scan_line_count():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("a\nb\nc\n")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files[0].line_count == 3


def test_scan_file_type_source():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files[0].file_type == FileType.SOURCE


def test_scan_file_type_test():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "test_app.py"), "w") as f:
            f.write("x=1")
        with open(os.path.join(tmp, "app_test.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        test_files = [sf for sf in result.files if sf.file_type == FileType.TEST]
        assert len(test_files) == 2


def test_scan_has_secrets_false():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files[0].has_secrets is False


def test_scan_has_secrets_true():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write('TOKEN = "sk-abc123xyzABCdef456"\n')
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        secret_files = [sf for sf in result.files if sf.has_secrets]
        assert len(secret_files) >= 1


def test_scan_parse_status_pending():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x=1")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.files[0].parse_status == ParseStatus.PENDING


def test_scan_binary_detection():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.py")
        with open(path, "wb") as f:
            f.write(b"\xff\xff")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        binary = [sf for sf in result.files if sf.is_binary]
        assert len(binary) >= 1


def test_ignore_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mod.py"), "w") as f:
            f.write("x=1")
        with open(os.path.join(tmp, "ignored.py"), "w") as f:
            f.write("y=2")
        with open(os.path.join(tmp, ".fcodeignore"), "w") as f:
            f.write("ignored.py\n")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) >= 1
        paths = [sf.file_path for sf in result.files]
        assert "mod.py" in paths
        assert "ignored.py" not in paths


def test_empty_file_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "empty.py"), "w") as f:
            f.write("")
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert len(result.files) == 0
        assert len(result.skipped) >= 1


def test_warning_count_on_secret():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "secret.py"), "w") as f:
            f.write('TOKEN = "ghp_ABCdef789GHIJklmnop"\n')
        repo = _repo(tmp)
        cfg = _config(tmp)
        result = scan(repo, cfg)
        assert result.warning_count >= 1
