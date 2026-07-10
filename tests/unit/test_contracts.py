"""Contract tests — verify WP0 shared contracts match documented behavior."""

from fcode.contracts import (
    ChunkType,
    Confidence,
    DiagnosticSeverity,
    ErrorCode,
    FileType,
    GraphNodeType,
    GraphRelation,
    HttpMethod,
    IndexPhase,
    IndexState,
    McpErrorCode,
    ParseStatus,
    SearchMode,
    SymbolType,
)


class TestEnums:
    def test_index_phase_order(self):
        phases = list(IndexPhase)
        expected = ["SCAN", "PARSE", "GRAPH", "CHUNK", "EMBED", "PERSIST"]
        assert [p.name for p in phases] == expected

    def test_index_state_values(self):
        assert IndexState.IDLE.value == "idle"
        assert IndexState.RUNNING.value == "running"
        assert IndexState.PASSED.value == "passed"
        assert IndexState.FAILED.value == "failed"
        assert IndexState.PARTIAL.value == "partial"

    def test_error_codes(self):
        assert ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value == "repository_limit_exceeded"
        assert ErrorCode.FILE_SKIPPED.value == "file_skipped"
        assert ErrorCode.NOT_IMPLEMENTED.value == "not_implemented"

    def test_mcp_error_codes(self):
        assert McpErrorCode.INVALID_INPUT.value == "invalid_input"
        assert McpErrorCode.NO_INDEX.value == "no_index"

    def test_confidence_values(self):
        assert Confidence.EXTRACTED.value == "extracted"
        assert Confidence.INFERRED.value == "inferred"
        assert Confidence.AMBIGUOUS.value == "ambiguous"

    def test_symbol_type_values(self):
        assert SymbolType.CLASS.value == "class"
        assert SymbolType.FUNCTION.value == "function"
        assert SymbolType.METHOD.value == "method"

    def test_graph_node_type_values(self):
        assert GraphNodeType.FILE.value == "file"
        assert GraphNodeType.SYMBOL.value == "symbol"
        assert GraphNodeType.CHUNK.value == "chunk"

    def test_graph_relation_values(self):
        assert GraphRelation.CONTAINS.value == "contains"
        assert GraphRelation.IMPORTS.value == "imports"
        assert GraphRelation.CALLS.value == "calls"
        assert GraphRelation.INHERITS.value == "inherits"
        assert GraphRelation.DEFINES.value == "defines"

    def test_parse_status_values(self):
        assert ParseStatus.PENDING.value == "pending"
        assert ParseStatus.PARSED.value == "parsed"
        assert ParseStatus.FAILED.value == "failed"
        assert ParseStatus.SKIPPED.value == "skipped"

    def test_chunk_type_values(self):
        assert ChunkType.CODE.value == "code"
        assert ChunkType.DOCSTRING.value == "docstring"
        assert ChunkType.COMMENT.value == "comment"
        assert ChunkType.MARKDOWN.value == "markdown"

    def test_file_type_values(self):
        assert FileType.PYTHON.value == "python"
        assert FileType.UNKNOWN.value == "unknown"

    def test_http_method_values(self):
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"

    def test_search_mode_values(self):
        assert SearchMode.EXACT.value == "exact"
        assert SearchMode.KEYWORD.value == "keyword"
        assert SearchMode.VECTOR.value == "vector"
        assert SearchMode.HYBRID.value == "hybrid"

    def test_diagnostic_severity_values(self):
        assert DiagnosticSeverity.WARNING.value == "warning"
        assert DiagnosticSeverity.ERROR.value == "error"


class TestModels:
    def test_doctor_result_all_passed(self):
        from fcode.contracts import DoctorCheck, DoctorResult
        r = DoctorResult(checks=[
            DoctorCheck(name="a", passed=True, message="ok"),
            DoctorCheck(name="b", passed=True, message="ok"),
        ])
        assert r.all_passed

    def test_doctor_result_not_all_passed(self):
        from fcode.contracts import DoctorCheck, DoctorResult
        r = DoctorResult(checks=[
            DoctorCheck(name="a", passed=True, message="ok"),
            DoctorCheck(name="b", passed=False, message="fail"),
        ])
        assert not r.all_passed

    def test_index_run_result_defaults(self):
        from fcode.contracts import IndexRunResult, IndexState, IndexPhase
        r = IndexRunResult(state=IndexState.IDLE, phase=IndexPhase.SCAN)
        assert r.state == IndexState.IDLE
        assert r.phase == IndexPhase.SCAN
        assert r.counts.scanned == 0

    def test_scanned_file_defaults(self):
        from fcode.contracts import ScannedFile, FileType
        f = ScannedFile(file_path="test.py", file_type=FileType.PYTHON, size_bytes=100)
        assert not f.is_binary
