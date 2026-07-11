"""Contract tests — verify WP0 shared contracts match documented behavior."""

import pytest

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

    def test_code_chunk_canonical_fields(self):
        from fcode.contracts import CodeChunk, ChunkType
        c = CodeChunk(
            chunk_id="id-1",
            file_id="file-1",
            chunk_type=ChunkType.FUNCTION,
            content="def foo(): pass",
            start_line=1,
            end_line=3,
            file_path="mod.py",
            language="Python",
            symbol_id="sym-1",
            symbol_name="foo",
            content_hash="abc",
            metadata={"has_secrets": False, "parse_status": "parsed"},
        )
        assert c.chunk_id == "id-1"
        assert c.file_id == "file-1"
        assert c.chunk_type == ChunkType.FUNCTION
        assert c.content == "def foo(): pass"
        assert c.start_line == 1
        assert c.end_line == 3
        assert c.language == "Python"
        assert c.file_path == "mod.py"
        assert c.symbol_id == "sym-1"
        assert c.symbol_name == "foo"
        assert c.content_hash == "abc"
        assert c.metadata["has_secrets"] is False

    def test_code_chunk_no_stale_fields(self):
        from fcode.contracts import CodeChunk
        assert not hasattr(CodeChunk, "text")
        assert not hasattr(CodeChunk, "source_file")
        assert not hasattr(CodeChunk, "embedding")

    def test_code_chunk_file_path_required(self):
        from fcode.contracts import CodeChunk, ChunkType
        with pytest.raises(TypeError, match="required positional argument|missing.*required.*argument"):
            CodeChunk(
                chunk_id="x", file_id="y", chunk_type=ChunkType.FILE_SUMMARY,
                content="z", start_line=1, end_line=1,
            )


# ── IndexCounts =───────────────────────────────────────────────────────────


class TestIndexCounts:
    def test_preserves_old_fields(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts(scanned=1, parsed=2, graph_nodes=3, graph_edges=4, chunks=5, embedded=6)
        assert c.scanned == 1
        assert c.parsed == 2
        assert c.graph_nodes == 3
        assert c.graph_edges == 4
        assert c.chunks == 5
        assert c.embedded == 6

    def test_contains_all_new_fields(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts(parse_errors=7, symbols=8, embedding_eligible=9,
                        embedding_skipped=10, embedding_failed=11, warnings=12, errors=13)
        assert c.parse_errors == 7
        assert c.symbols == 8
        assert c.embedding_eligible == 9
        assert c.embedding_skipped == 10
        assert c.embedding_failed == 11
        assert c.warnings == 12
        assert c.errors == 13

    def test_defaults_are_zero(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts()
        for field_name in c.__dataclass_fields__:
            assert getattr(c, field_name) == 0

    def test_validation_accepts_zero_values(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts()
        c.validate()  # should not raise

    def test_rejects_negative_values(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts(scanned=-1)
        with pytest.raises(ValueError):
            c.validate()

    def test_rejects_booleans(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts(scanned=True)  # type: ignore
        with pytest.raises(ValueError):
            c.validate()

    def test_rejects_non_integers(self):
        from fcode.contracts import IndexCounts
        c = IndexCounts(scanned="five")  # type: ignore
        with pytest.raises(ValueError):
            c.validate()


# ── IndexDiagnostic ────────────────────────────────────────────────────────


class TestIndexDiagnostic:
    def test_exact_fields(self):
        from fcode.contracts import IndexDiagnostic, DiagnosticSeverity
        from fcode.contracts.enums import IndexPhase
        d = IndexDiagnostic(
            code="test_code",
            message="test message",
            phase=IndexPhase.SCAN,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
            repo_relative_path="src/main.py",
            details="some details",
        )
        assert d.code == "test_code"
        assert d.message == "test message"
        assert d.phase == IndexPhase.SCAN
        assert not d.recoverable
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.repo_relative_path == "src/main.py"
        assert d.details == "some details"

    def test_warning_recoverable_combination_validates(self):
        from fcode.contracts import IndexDiagnostic, DiagnosticSeverity
        d = IndexDiagnostic(code="w", message="warning", recoverable=True, severity=DiagnosticSeverity.WARNING)
        d.validate()

    def test_error_nonrecoverable_combination_validates(self):
        from fcode.contracts import IndexDiagnostic, DiagnosticSeverity
        d = IndexDiagnostic(code="e", message="error", recoverable=False, severity=DiagnosticSeverity.ERROR)
        d.validate()

    def test_inconsistent_severity_recoverable_rejected(self):
        from fcode.contracts import IndexDiagnostic, DiagnosticSeverity
        d = IndexDiagnostic(code="x", message="bad", recoverable=False, severity=DiagnosticSeverity.WARNING)
        with pytest.raises(ValueError):
            d.validate()
        d2 = IndexDiagnostic(code="x", message="bad2", recoverable=True, severity=DiagnosticSeverity.ERROR)
        with pytest.raises(ValueError):
            d2.validate()

    def test_absolute_diagnostic_path_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="x", message="test", repo_relative_path="/absolute/path")
        with pytest.raises(ValueError):
            d.validate()

    def test_traversal_diagnostic_path_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="x", message="test", repo_relative_path="src/../secret")
        with pytest.raises(ValueError):
            d.validate()

    def test_backslash_diagnostic_path_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="x", message="test", repo_relative_path="src\\main.py")
        with pytest.raises(ValueError):
            d.validate()

    def test_empty_diagnostic_code_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="", message="test")
        with pytest.raises(ValueError):
            d.validate()

    def test_empty_diagnostic_message_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="x", message="")
        with pytest.raises(ValueError):
            d.validate()

    def test_message_over_500_characters_rejected(self):
        from fcode.contracts import IndexDiagnostic
        d = IndexDiagnostic(code="x", message="x" * 501)
        with pytest.raises(ValueError):
            d.validate()


# ── IndexRunResult =────────────────────────────────────────────────────────


class TestIndexRunResult:
    def test_defaults_to_pending_and_phase_none(self):
        from fcode.contracts import IndexRunResult, IndexState
        r = IndexRunResult()
        assert r.state == IndexState.PENDING
        assert r.phase is None
        assert r.counts.scanned == 0
        assert r.diagnostics == []
        assert r.errors == []

    def test_validates_legal_state_phase_combinations(self):
        from fcode.contracts import IndexRunResult, IndexState, IndexPhase
        r = IndexRunResult(state=IndexState.SCANNING, phase=IndexPhase.SCAN)
        r.validate()

    def test_rejects_illegal_state_phase_combinations(self):
        from fcode.contracts import IndexRunResult, IndexState, IndexPhase
        r = IndexRunResult(state=IndexState.PENDING, phase=IndexPhase.SCAN)
        with pytest.raises(ValueError):
            r.validate()

    def test_complete_rejects_fatal_diagnostics(self):
        from fcode.contracts import IndexRunResult, IndexState, IndexPhase
        from fcode.contracts import IndexDiagnostic, DiagnosticSeverity
        fatal = IndexDiagnostic(code="fatal", message="fatal error", recoverable=False,
                                severity=DiagnosticSeverity.ERROR)
        r = IndexRunResult(state=IndexState.COMPLETE, phase=IndexPhase.PERSIST,
                           diagnostics=[fatal])
        with pytest.raises(ValueError):
            r.validate()

    def test_error_requires_fatal_evidence(self):
        from fcode.contracts import IndexRunResult, IndexState, IndexPhase
        r = IndexRunResult(state=IndexState.ERROR, phase=IndexPhase.SCAN)
        with pytest.raises(ValueError):
            r.validate()

    def test_errors_compatibility_field_remains_present(self):
        from fcode.contracts import IndexRunResult
        r = IndexRunResult(errors=["something went wrong"])
        assert r.errors == ["something went wrong"]
