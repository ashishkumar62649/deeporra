"""Tests for IndexService.build_through_chunking — config validation, scan, parse, chunk."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fcode.contracts import (
    ChunkType,
    CodeChunk,
    DiagnosticSeverity,
    ErrorCode,
    FCodeConfig,
    IndexPhase,
    IndexState,
    ParseStatus,
    ParsedFile,
    ParsedRoute,
    ParsedSymbol,
    ScanResult,
    ScannedFile,
    SymbolType,
)
from fcode.indexing.index_service import IndexService
from fcode.contracts.enums import HttpMethod, FileType


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_config():
    return FCodeConfig(repo_path=".", max_files=10000, max_size_bytes=52428800)


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "main.py").write_text("x = 1")
        yield d


# ── Constructor ──────────────────────────────────────────────────────────────


class TestConstructor:
    def test_none_scanner_raises_typeerror(self):
        with pytest.raises(TypeError):
            IndexService(scanner=None, parser=MagicMock(), chunker=MagicMock())

    def test_none_parser_raises_typeerror(self):
        with pytest.raises(TypeError):
            IndexService(scanner=MagicMock(), parser=None, chunker=MagicMock())

    def test_none_chunker_raises_typeerror(self):
        with pytest.raises(TypeError):
            IndexService(scanner=MagicMock(), parser=MagicMock(), chunker=None)

    def test_backward_compat_no_encoder_graph_builder(self):
        svc = IndexService(scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock())
        assert svc._encoder is None
        assert svc._graph_builder is None

    def test_backward_compat_with_encoder(self):
        svc = IndexService(
            scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock(),
            encoder=MagicMock(),
        )
        assert svc._encoder is not None

    def test_backward_compat_with_graph_builder(self):
        svc = IndexService(
            scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock(),
            graph_builder=MagicMock(),
        )
        assert svc._graph_builder is not None

    def test_backward_compat_with_both(self):
        svc = IndexService(
            scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock(),
            encoder=MagicMock(), graph_builder=MagicMock(),
        )
        assert svc._encoder is not None
        assert svc._graph_builder is not None


@pytest.mark.parametrize(
    "stage",
    ["scanner", "parser", "chunker"],
)
@pytest.mark.parametrize(
    "control", [KeyboardInterrupt("scan"), SystemExit("exit"), GeneratorExit("close")],
    ids=["keyboard_interrupt", "system_exit", "generator_exit"],
)
def test_process_control_exceptions_propagate_from_step2(stage, control):
    scanner = MagicMock()
    scanner.scan.return_value = ScanResult(
        files=[_make_scanned(parse_status=ParseStatus.PENDING, is_binary=False)],
        eligible_file_count=1,
        total_count=1,
        eligible_total_bytes=1,
    )
    parser = MagicMock()
    parser.parse.return_value = ParsedFile(
        file_id="f1", file_path="mod.py", status=ParseStatus.PARSED,
    )
    chunker = MagicMock()
    chunker.chunk.return_value = []
    {"scanner": scanner.scan, "parser": parser.parse, "chunker": chunker.chunk}[stage].side_effect = control

    with pytest.raises(type(control)) as raised:
        IndexService(scanner, parser, chunker).build_through_chunking(FCodeConfig(repo_path="."))

    assert raised.value is control


# ── validate_config ──────────────────────────────────────────────────────────


class TestValidateConfig:
    def test_missing_repo_path(self):
        config = FCodeConfig(repo_path="")
        d, msg = IndexService._validate_config(config)
        assert d.code == ErrorCode.INVALID_REPOSITORY_PATH.value
        assert not d.recoverable

    def test_nonexistent_repo_path(self):
        config = FCodeConfig(repo_path="/nonexistent/path")
        d, msg = IndexService._validate_config(config)
        assert d.code == ErrorCode.INVALID_REPOSITORY_PATH.value

    def test_repo_path_is_file_not_dir(self, temp_repo):
        fp = Path(temp_repo, "main.py")
        config = FCodeConfig(repo_path=str(fp))
        d, msg = IndexService._validate_config(config)
        assert d.code == ErrorCode.INVALID_REPOSITORY_PATH.value

    def test_valid_repo_path_returns_none(self, temp_repo):
        config = FCodeConfig(repo_path=temp_repo)
        assert IndexService._validate_config(config) is None

    def test_bool_max_files(self):
        config = FCodeConfig(repo_path=".", max_files=True)
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"

    def test_non_int_max_files(self):
        config = FCodeConfig(repo_path=".", max_files="ten")
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"

    def test_zero_max_files(self):
        config = FCodeConfig(repo_path=".", max_files=0)
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"

    def test_negative_max_files(self):
        config = FCodeConfig(repo_path=".", max_files=-1)
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"

    def test_bool_max_size_bytes(self):
        config = FCodeConfig(repo_path=".", max_size_bytes=True)
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"

    def test_zero_max_size_bytes(self):
        config = FCodeConfig(repo_path=".", max_size_bytes=0)
        d, msg = IndexService._validate_config(config)
        assert d.code == "config_invalid"


# ── validate_scan_result ─────────────────────────────────────────────────────


def _make_scanned(pid="f1", path="mod.py", **kw):
    return ScannedFile(file_id=pid, file_path=path, **kw)


class TestValidateScanResult:
    def test_wrong_type(self):
        d, msg = IndexService._validate_scan_result("not a scan result", None)
        assert d.code == ErrorCode.SCAN_FAILED.value
        assert not d.recoverable

    def test_empty_file_id(self):
        sr = ScanResult(files=[_make_scanned(pid="")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_duplicate_file_id(self):
        sr = ScanResult(files=[_make_scanned(), _make_scanned()])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_empty_path(self):
        sr = ScanResult(files=[_make_scanned(path="")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_absolute_path(self):
        sr = ScanResult(files=[_make_scanned(path="/abs/mod.py")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_path_traversal(self):
        sr = ScanResult(files=[_make_scanned(path="src/../mod.py")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_backslash_path(self):
        sr = ScanResult(files=[_make_scanned(path="src\\mod.py")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_duplicate_paths(self):
        sr = ScanResult(files=[_make_scanned(pid="f1", path="a.py"), _make_scanned(pid="f2", path="a.py")])
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_eligible_count_mismatch(self):
        sr = ScanResult(files=[_make_scanned()], eligible_file_count=2, total_count=1)
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_total_count_mismatch(self):
        sr = ScanResult(files=[_make_scanned()], total_count=2, eligible_file_count=1)
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_negative_eligible_count(self):
        sr = ScanResult(files=[_make_scanned()], eligible_file_count=-1, total_count=1)
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_negative_total_bytes(self):
        sr = ScanResult(files=[_make_scanned()], eligible_total_bytes=-1, eligible_file_count=1, total_count=1)
        d, msg = IndexService._validate_scan_result(sr, None)
        assert d.code == ErrorCode.SCAN_FAILED.value

    def test_over_max_files(self):
        config = FCodeConfig(repo_path=".", max_files=1)
        sr = ScanResult(files=[_make_scanned(), _make_scanned(pid="f2", path="b.py")],
                        eligible_file_count=2, total_count=2, eligible_total_bytes=100)
        d, msg = IndexService._validate_scan_result(sr, config)
        assert d.code == ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value

    def test_over_max_bytes(self):
        config = FCodeConfig(repo_path=".", max_size_bytes=50)
        sr = ScanResult(files=[_make_scanned()],
                        eligible_file_count=1, total_count=1, eligible_total_bytes=100)
        d, msg = IndexService._validate_scan_result(sr, config)
        assert d.code == ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value

    def test_skipped_limit_exceeded(self):
        from fcode.contracts import SkippedFileDiagnostic
        sr = ScanResult(files=[_make_scanned()], skipped=[SkippedFileDiagnostic(file_path="x.py", reason="repository_limit_exceeded")],
                        eligible_file_count=1, total_count=1, eligible_total_bytes=100)
        d, msg = IndexService._validate_scan_result(sr, FCodeConfig())
        assert d.code == ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value

    def test_valid_scan_result(self):
        sr = ScanResult(files=[_make_scanned()], eligible_file_count=1, total_count=1, eligible_total_bytes=100)
        assert IndexService._validate_scan_result(sr, FCodeConfig()) is None

    def test_duplicate_paths_different(self):
        sr = ScanResult(files=[_make_scanned(pid="f1", path="a.py"), _make_scanned(pid="f2", path="b.py")],
                        eligible_file_count=2, total_count=2, eligible_total_bytes=100)
        assert IndexService._validate_scan_result(sr, FCodeConfig()) is None


# ── convert_scanner_warnings ─────────────────────────────────────────────────


class TestConvertScannerWarnings:
    def test_empty_warnings(self):
        assert IndexService._convert_scanner_warnings(ScanResult()) == []

    def test_converts_dict_warning(self):
        sr = ScanResult(warnings=[{"code": "w1", "message": "something skipped", "file_path": "src/a.py"}])
        diags = IndexService._convert_scanner_warnings(sr)
        assert len(diags) == 1
        assert diags[0].code == "w1"
        assert diags[0].message == "something skipped"
        assert diags[0].phase == IndexPhase.SCAN
        assert diags[0].recoverable
        assert diags[0].severity == DiagnosticSeverity.WARNING

    def test_fallback_for_non_dict_warning(self):
        sr = ScanResult(warnings=["just a string"])
        diags = IndexService._convert_scanner_warnings(sr)
        assert len(diags) == 1
        assert diags[0].code == ErrorCode.FILE_SKIPPED.value
        assert diags[0].recoverable

    def test_truncates_long_message(self):
        long_msg = "x" * 1000
        sr = ScanResult(warnings=[{"message": long_msg}])
        diags = IndexService._convert_scanner_warnings(sr)
        assert len(diags[0].message) == 500

    def test_rejects_absolute_path_in_warning(self):
        sr = ScanResult(warnings=[{"repo_relative_path": "/abs/path"}])
        diags = IndexService._convert_scanner_warnings(sr)
        assert diags[0].repo_relative_path is None


# ── validate_parse_result ────────────────────────────────────────────────────


class TestValidateParseResult:
    def test_wrong_type(self):
        sf = _make_scanned()
        d, msg = IndexService._validate_parse_result("not a ParsedFile", sf)
        assert d.code == ErrorCode.PARSE_FAILED.value
        assert not d.recoverable

    def test_mismatched_file_id(self):
        sf = _make_scanned(pid="f1")
        pf = ParsedFile(file_id="f2", file_path="mod.py", status=ParseStatus.PARSED)
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_mismatched_file_path(self):
        sf = _make_scanned(path="a.py")
        pf = ParsedFile(file_id="f1", file_path="b.py", status=ParseStatus.PARSED)
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_pending_status_rejected(self):
        sf = _make_scanned()
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PENDING)
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_valid_parsed(self):
        sf = _make_scanned()
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)
        assert IndexService._validate_parse_result(pf, sf) is None

    def test_valid_error_status(self):
        sf = _make_scanned()
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.ERROR)
        assert IndexService._validate_parse_result(pf, sf) is None

    def test_valid_not_applicable(self):
        sf = _make_scanned()
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.NOT_APPLICABLE)
        assert IndexService._validate_parse_result(pf, sf) is None

    def test_symbol_without_id(self):
        sf = _make_scanned()
        sym = ParsedSymbol(name="foo", symbol_type=SymbolType.FUNCTION, symbol_id="")
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED, symbols=[sym])
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_duplicate_symbol_ids(self):
        sf = _make_scanned()
        sym = ParsedSymbol(name="foo", symbol_type=SymbolType.FUNCTION, symbol_id="s1")
        sym2 = ParsedSymbol(name="bar", symbol_type=SymbolType.CLASS, symbol_id="s1")
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED, symbols=[sym, sym2])
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_route_without_id(self):
        sf = _make_scanned()
        rt = ParsedRoute(method=HttpMethod.GET, route_path="/api", handler_function="handler", route_id="")
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED, routes=[rt])
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value

    def test_duplicate_route_ids(self):
        sf = _make_scanned()
        rt1 = ParsedRoute(route_id="r1", method=HttpMethod.GET, route_path="/a", handler_function="ha")
        rt2 = ParsedRoute(route_id="r1", method=HttpMethod.POST, route_path="/b", handler_function="hb")
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED, routes=[rt1, rt2])
        d, msg = IndexService._validate_parse_result(pf, sf)
        assert d.code == ErrorCode.PARSE_FAILED.value


# ── validate_chunks ──────────────────────────────────────────────────────────


class TestValidateChunks:
    def test_wrong_type(self):
        d, msg = IndexService._validate_chunks("not a list", [])
        assert d.code == "chunk_failed"
        assert not d.recoverable

    def test_non_codechunk_item(self):
        d, msg = IndexService._validate_chunks(["string"], [])
        assert d.code == "chunk_failed"

    def test_missing_chunk_id(self):
        c = CodeChunk(chunk_id="", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="m.py")
        d, msg = IndexService._validate_chunks([c], [])
        assert d.code == "chunk_failed"

    def test_duplicate_chunk_ids(self):
        c1 = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                       content="a", start_line=1, end_line=2, file_path="m.py")
        c2 = CodeChunk(chunk_id="c1", file_id="f2", chunk_type=ChunkType.FUNCTION,
                       content="b", start_line=3, end_line=4, file_path="n.py")
        d, msg = IndexService._validate_chunks([c1, c2], [])
        assert d.code == "chunk_failed"

    def test_unknown_file_id(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="unknown", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="m.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_unknown_file_path(self):
        sf = _make_scanned(path="known.py")
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="unknown.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_absolute_path(self):
        sf = _make_scanned(path="m.py")
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="/abs/m.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_path_traversal(self):
        sf = _make_scanned(path="m.py")
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="src/../m.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_backslash_path(self):
        sf = _make_scanned(path="m.py")
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="src\\m.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_invalid_start_line(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=0, end_line=5, file_path="mod.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_end_line_before_start(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=5, end_line=3, file_path="mod.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_empty_content(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="   ", start_line=1, end_line=5, file_path="mod.py")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_wrong_content_hash(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="mod.py",
                      content_hash="wronghash")
        d, msg = IndexService._validate_chunks([c], [sf])
        assert d.code == "chunk_failed"

    def test_valid_chunk(self):
        import hashlib
        sf = _make_scanned()
        content = "def foo(): pass"
        ch = hashlib.sha256(content.encode("utf-8")).hexdigest()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content=content, start_line=1, end_line=1, file_path="mod.py",
                      content_hash=ch)
        assert IndexService._validate_chunks([c], [sf]) is None

    def test_empty_content_hash_skips_validation(self):
        sf = _make_scanned()
        c = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                      content="code", start_line=1, end_line=5, file_path="mod.py",
                      content_hash="")
        assert IndexService._validate_chunks([c], [sf]) is None


# ── build_through_chunking: failure scenarios ────────────────────────────────


class TestBuildThroughChunkingFailures:
    def test_type_error_on_non_config(self):
        svc = IndexService(scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock())
        with pytest.raises(TypeError):
            svc.build_through_chunking(config="not a config")  # type: ignore

    def test_config_validation_fails(self):
        svc = IndexService(scanner=MagicMock(), parser=MagicMock(), chunker=MagicMock())
        config = FCodeConfig(repo_path="")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR
        assert not result.persistent_replacement_started
        assert not result.chunks
        assert result.scan_result is None

    def test_scanner_exception(self):
        scanner = MagicMock()
        scanner.scan.side_effect = RuntimeError("boom")
        svc = IndexService(scanner=scanner, parser=MagicMock(), chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR
        assert not result.persistent_replacement_started

    def test_scanner_invalid_result_type(self):
        scanner = MagicMock()
        scanner.scan.return_value = "not a scan result"
        svc = IndexService(scanner=scanner, parser=MagicMock(), chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR
        assert not result.persistent_replacement_started

    def test_scanner_returns_duplicate_ids(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(), _make_scanned()],
            eligible_file_count=2, total_count=2, eligible_total_bytes=100,
        )
        svc = IndexService(scanner=scanner, parser=MagicMock(), chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR

    def test_parser_exception(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(pid="f1", path="mod.py")],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        parser = MagicMock()
        parser.parse.side_effect = ValueError("parse crash")
        svc = IndexService(scanner=scanner, parser=parser, chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR
        assert not result.persistent_replacement_started

    def test_parser_returns_invalid_type(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(pid="f1", path="mod.py")],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        parser = MagicMock()
        parser.parse.return_value = "not a parsed file"
        svc = IndexService(scanner=scanner, parser=parser, chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR

    def test_parser_returns_mismatched_id(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(pid="f1", path="mod.py")],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        parser = MagicMock()
        parser.parse.return_value = ParsedFile(file_id="wrong", file_path="mod.py", status=ParseStatus.PARSED)
        svc = IndexService(scanner=scanner, parser=parser, chunker=MagicMock())
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR

    def test_chunker_exception(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(pid="f1", path="mod.py")],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        parser = MagicMock()
        parser.parse.return_value = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)
        chunker = MagicMock()
        chunker.chunk.side_effect = RuntimeError("chunk crash")
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR
        assert not result.persistent_replacement_started

    def test_chunker_returns_non_list(self):
        scanner = MagicMock()
        scanner.scan.return_value = ScanResult(
            files=[_make_scanned(pid="f1", path="mod.py")],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        parser = MagicMock()
        parser.parse.return_value = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)
        chunker = MagicMock()
        chunker.chunk.return_value = "not a list"
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        config = FCodeConfig(repo_path=".")
        result = svc.build_through_chunking(config)
        assert result.run_result.state == IndexState.ERROR


# ── build_through_chunking: happy path ───────────────────────────────────────


class TestBuildThroughChunkingHappyPath:
    def test_basic_happy_path(self, temp_repo):
        sf = _make_scanned(pid="f1", path="mod.py", parse_status=ParseStatus.PENDING,
                           is_binary=False, file_type=FileType.SOURCE)
        scan_result = ScanResult(
            files=[sf],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)

        import hashlib
        chunk_content = "def foo(): pass"
        ch = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
        chunk = CodeChunk(
            chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
            content=chunk_content, start_line=1, end_line=1, file_path="mod.py",
            content_hash=ch,
        )

        scanner = MagicMock()
        scanner.scan.return_value = scan_result
        parser = MagicMock()
        parser.parse.return_value = pf
        chunker = MagicMock()
        chunker.chunk.return_value = [chunk]

        config = FCodeConfig(repo_path=temp_repo, max_files=10000, max_size_bytes=52428800)
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        result = svc.build_through_chunking(config)

        assert result.run_result.state == IndexState.CHUNKING
        assert result.completed_phase == IndexPhase.PARSE
        assert result.run_result.phase == IndexPhase.CHUNK
        assert not result.persistent_replacement_started
        assert result.run_result.counts.scanned == 1
        assert result.run_result.counts.parsed == 1
        assert result.run_result.counts.chunks == 1
        assert len(result.chunks) == 1
        assert len(result.parsed_files) == 1
        assert result.scan_result is not None
        assert len(result.run_result.diagnostics) == 0

    def test_parse_error_still_successful(self, temp_repo):
        sf = _make_scanned(pid="f1", path="mod.py", parse_status=ParseStatus.PENDING,
                           is_binary=False, file_type=FileType.SOURCE)
        scan_result = ScanResult(
            files=[sf],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.ERROR, errors=["syntax error"])

        scanner = MagicMock()
        scanner.scan.return_value = scan_result
        parser = MagicMock()
        parser.parse.return_value = pf
        chunker = MagicMock()
        chunker.chunk.return_value = []

        config = FCodeConfig(repo_path=temp_repo, max_files=10000, max_size_bytes=52428800)
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        result = svc.build_through_chunking(config)

        assert result.run_result.state == IndexState.CHUNKING
        assert result.run_result.counts.scanned == 1
        assert result.run_result.counts.parsed == 0
        assert result.run_result.counts.parse_errors == 1
        warnings = [d for d in result.run_result.diagnostics if d.severity == DiagnosticSeverity.WARNING]
        assert len(warnings) == 1

    def test_non_python_files_not_parsed(self, temp_repo):
        sf = _make_scanned(pid="f1", path="notes.md", parse_status=ParseStatus.NOT_APPLICABLE,
                           is_binary=False, file_type=FileType.DOC)
        scan_result = ScanResult(
            files=[sf],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )

        scanner = MagicMock()
        scanner.scan.return_value = scan_result
        parser = MagicMock()
        chunker = MagicMock()
        chunker.chunk.return_value = []

        config = FCodeConfig(repo_path=temp_repo, max_files=10000, max_size_bytes=52428800)
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        result = svc.build_through_chunking(config)

        assert result.run_result.state == IndexState.CHUNKING
        assert result.run_result.counts.scanned == 1
        assert result.run_result.counts.parsed == 0
        parser.parse.assert_not_called()

    def test_state_history(self, temp_repo):
        sf = _make_scanned(pid="f1", path="mod.py", parse_status=ParseStatus.PENDING,
                           is_binary=False, file_type=FileType.SOURCE)
        scan_result = ScanResult(
            files=[sf],
            eligible_file_count=1, total_count=1, eligible_total_bytes=100,
        )
        pf = ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)
        chunk = CodeChunk(chunk_id="c1", file_id="f1", chunk_type=ChunkType.FUNCTION,
                          content="x", start_line=1, end_line=1, file_path="mod.py")

        scanner = MagicMock()
        scanner.scan.return_value = scan_result
        parser = MagicMock()
        parser.parse.return_value = pf
        chunker = MagicMock()
        chunker.chunk.return_value = [chunk]

        config = FCodeConfig(repo_path=temp_repo, max_files=10000, max_size_bytes=52428800)
        svc = IndexService(scanner=scanner, parser=parser, chunker=chunker)
        result = svc.build_through_chunking(config)

        assert result.state_history == (
            IndexState.PENDING,
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
        )
