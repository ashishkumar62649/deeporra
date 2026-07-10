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
        assert IndexState.PENDING.value == "pending"
        assert IndexState.SCANNING.value == "scanning"
        assert IndexState.PARSING.value == "parsing"
        assert IndexState.CHUNKING.value == "chunking"
        assert IndexState.EMBEDDING.value == "embedding"
        assert IndexState.GRAPHING.value == "graphing"
        assert IndexState.STORING.value == "storing"
        assert IndexState.COMPLETE.value == "complete"
        assert IndexState.ERROR.value == "error"

    def test_error_codes(self):
        assert ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value == "repository_limit_exceeded"
        assert ErrorCode.FILE_SKIPPED.value == "file_skipped"
        assert ErrorCode.NOT_IMPLEMENTED.value == "not_implemented"

    def test_mcp_error_codes(self):
        assert McpErrorCode.INVALID_INPUT.value == "invalid_input"
        assert McpErrorCode.NO_INDEX.value == "no_index"

    def test_confidence_values(self):
        assert Confidence.EXTRACTED.value == "EXTRACTED"
        assert Confidence.INFERRED.value == "INFERRED"
        assert Confidence.AMBIGUOUS.value == "AMBIGUOUS"

    def test_symbol_type_values(self):
        assert SymbolType.FUNCTION.value == "function"
        assert SymbolType.CLASS.value == "class"
        assert SymbolType.METHOD.value == "method"
        assert SymbolType.ROUTE.value == "route"
        assert SymbolType.VARIABLE.value == "variable"

    def test_graph_node_type_values(self):
        assert GraphNodeType.FILE.value == "file"
        assert GraphNodeType.FUNCTION.value == "function"
        assert GraphNodeType.CLASS.value == "class"
        assert GraphNodeType.METHOD.value == "method"
        assert GraphNodeType.ROUTE.value == "route"
        assert GraphNodeType.IMPORT.value == "import"
        assert GraphNodeType.TEST.value == "test"

    def test_graph_relation_values(self):
        assert GraphRelation.DEFINES.value == "defines"
        assert GraphRelation.IMPORTS.value == "imports"
        assert GraphRelation.INHERITS.value == "inherits"
        assert GraphRelation.CALLS.value == "calls"
        assert GraphRelation.TESTS.value == "tests"
        assert GraphRelation.HANDLES_ROUTE.value == "handles_route"

    def test_parse_status_values(self):
        assert ParseStatus.PENDING.value == "pending"
        assert ParseStatus.PARSED.value == "parsed"
        assert ParseStatus.ERROR.value == "error"
        assert ParseStatus.NOT_APPLICABLE.value == "not_applicable"

    def test_chunk_type_values(self):
        assert ChunkType.FILE_SUMMARY.value == "file_summary"
        assert ChunkType.FUNCTION.value == "function"
        assert ChunkType.CLASS.value == "class"
        assert ChunkType.METHOD.value == "method"
        assert ChunkType.ROUTE.value == "route"
        assert ChunkType.TEST.value == "test"
        assert ChunkType.CONFIG.value == "config"
        assert ChunkType.README_SECTION.value == "readme_section"

    def test_file_type_values(self):
        assert FileType.SOURCE.value == "source"
        assert FileType.TEST.value == "test"
        assert FileType.CONFIG.value == "config"
        assert FileType.DOC.value == "doc"

    def test_http_method_values(self):
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"

    def test_search_mode_values(self):
        assert SearchMode.FTS5.value == "fts5"
        assert SearchMode.LIKE_FALLBACK.value == "like_fallback"

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
        r = IndexRunResult(state=IndexState.PENDING, phase=IndexPhase.SCAN)
        assert r.state == IndexState.PENDING
        assert r.phase == IndexPhase.SCAN
        assert r.counts.scanned == 0

    def test_scanned_file_defaults(self):
        from fcode.contracts import ScannedFile, FileType
        f = ScannedFile(file_path="test.py", file_type=FileType.SOURCE, size_bytes=100)
        assert not f.is_binary
