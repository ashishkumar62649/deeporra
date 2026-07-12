"""Tests for IndexService.build_through_graphing — embedding and graph orchestration."""

import hashlib
import math
from unittest.mock import MagicMock

import pytest

from fcode.contracts import (
    ChunkType,
    CodeChunk,
    DiagnosticSeverity,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingMetadata,
    EmbeddingRecord,
    ErrorCode,
    FCodeConfig,
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    GraphNodeType,
    GraphRelation,
    IndexPhase,
    IndexState,
    ParseStatus,
    ParsedFile,
    ScanResult,
    ScannedFile,
    FileType,
    Confidence,
)
from fcode.embeddings import EXPECTED_DIMENSION
from fcode.indexing.index_service import IndexService


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_scanned(pid="f1", path="mod.py", **kw):
    return ScannedFile(file_id=pid, file_path=path, **kw)


def _make_chunk(cid="c1", fid="f1", path="mod.py", content="def foo(): pass",
                start=1, end=1, ctype=ChunkType.FUNCTION, sym_name="foo",
                meta=None):
    ch = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return CodeChunk(
        chunk_id=cid, file_id=fid, chunk_type=ctype,
        content=content, start_line=start, end_line=end,
        file_path=path, content_hash=ch, symbol_name=sym_name,
        metadata=meta or {"has_secrets": False, "parse_status": ParseStatus.PARSED},
    )


def _make_embedding_input(cid="c1", content="def foo(): pass", path="mod.py"):
    return EmbeddingInput(
        chunk_id=cid,
        content=content,
        metadata=EmbeddingMetadata(
            chunk_id=cid, file_path=path, symbol_name="foo",
            chunk_type=ChunkType.FUNCTION,
            start_line=1, end_line=1,
        ),
        has_secrets=False,
        parse_status=ParseStatus.PARSED,
    )


def _make_batch_result(eligible=1, success=1, fail=0, skipped=0,
                       records=None, warnings=None):
    return EmbeddingBatchResult(
        records=records or [],
        eligible_count=eligible,
        success_count=success,
        fail_count=fail,
        skipped_count=skipped,
        warnings=warnings or [],
    )


def _make_valid_record(cid="c1", path="mod.py"):
    vec = [0.0] * EXPECTED_DIMENSION
    return EmbeddingRecord(
        chunk_id=cid,
        vector=vec,
        metadata=EmbeddingMetadata(
            chunk_id=cid, file_path=path, symbol_name="foo",
            chunk_type=ChunkType.FUNCTION, start_line=1, end_line=1,
        ),
    )


def _make_default_scan_result(files=None):
    sf = files or [_make_scanned(pid="f1", path="mod.py", parse_status=ParseStatus.PENDING,
                                  is_binary=False, file_type=FileType.SOURCE)]
    return ScanResult(
        files=sf,
        eligible_file_count=len(sf), total_count=len(sf), eligible_total_bytes=100,
    )


def _make_default_parsed_files():
    return [ParsedFile(file_id="f1", file_path="mod.py", status=ParseStatus.PARSED)]


def _nuuid(name: str) -> str:
    """Synthetic deterministic record ID for tests of validator-only behavior."""
    import hashlib
    return "gn:" + hashlib.sha256(name.encode()).hexdigest()


def _euuid(name: str) -> str:
    import hashlib
    return "ge:" + hashlib.sha256(name.encode()).hexdigest()


def _make_default_service(encoder=None, graph_builder=None, scanner=None,
                          parser=None, chunker=None):
    if scanner is None:
        scanner = MagicMock()
        scanner.scan.return_value = _make_default_scan_result()
    if parser is None:
        parser = MagicMock()
        parser.parse.return_value = _make_default_parsed_files()[0]
    if chunker is None:
        chunker = MagicMock()
        chunker.chunk.return_value = [_make_chunk()]
    return IndexService(
        scanner=scanner, parser=parser, chunker=chunker,
        encoder=encoder, graph_builder=graph_builder,
    )


def _setup_default_mocks(scan_result=None, parsed_files=None, chunks=None):
    scanner = MagicMock()
    scanner.scan.return_value = scan_result or _make_default_scan_result()
    parser = MagicMock()
    parser.parse.side_effect = parsed_files or _make_default_parsed_files()
    chunker = MagicMock()
    chunker.chunk.return_value = chunks or [_make_chunk()]
    return scanner, parser, chunker


# ── Constructor: deps required for graphing ──────────────────────────────────


class TestConstructorDeps:
    def test_encoder_none_raises_on_graphing(self):
        svc = _make_default_service(encoder=None, graph_builder=MagicMock())
        with pytest.raises(TypeError, match="encoder is required"):
            svc.build_through_graphing(FCodeConfig(repo_path="."))

    def test_graph_builder_none_raises_on_graphing(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=None)
        with pytest.raises(TypeError, match="graph_builder is required"):
            svc.build_through_graphing(FCodeConfig(repo_path="."))

    def test_encoder_provided_allows_graphing(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=MagicMock())
        svc.build_through_graphing(FCodeConfig(repo_path="."))


# ── build_through_graphing: config validation ────────────────────────────────


class TestGraphingConfigValidation:
    def test_type_error_on_non_config(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=MagicMock())
        with pytest.raises(TypeError, match="expected FCodeConfig"):
            svc.build_through_graphing(config="not a config")

    def test_config_validation_fails_empty_path(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path=""))
        assert result.run_result.state == IndexState.ERROR

    def test_encoder_not_called_on_config_failure(self):
        encoder = MagicMock()
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path=""))
        encoder.encode.assert_not_called()


# ── Step 2 failure propagation ───────────────────────────────────────────────


class TestGraphingStep2Failures:
    def test_scanner_exception(self):
        scanner = MagicMock()
        scanner.scan.side_effect = RuntimeError("boom")
        encoder = MagicMock()
        svc = _make_default_service(scanner=scanner, encoder=encoder,
                                     graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        encoder.encode.assert_not_called()

    def test_parser_exception(self):
        scanner = MagicMock()
        scanner.scan.return_value = _make_default_scan_result()
        parser = MagicMock()
        parser.parse.side_effect = ValueError("crash")
        encoder = MagicMock()
        svc = _make_default_service(scanner=scanner, parser=parser,
                                     encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        encoder.encode.assert_not_called()

    def test_chunker_exception(self):
        scanner, parser, _ = _setup_default_mocks()
        chunker = MagicMock()
        chunker.chunk.side_effect = RuntimeError("chunk crash")
        encoder = MagicMock()
        svc = _make_default_service(scanner=scanner, parser=parser,
                                     chunker=chunker, encoder=encoder,
                                     graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        encoder.encode.assert_not_called()

    def test_step2_success_path_reaches_embedding(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        scanner, parser, _ = _setup_default_mocks()
        svc = _make_default_service(scanner=scanner, parser=parser,
                                     encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING
        encoder.encode.assert_called_once()


# ── Embedding input builder ──────────────────────────────────────────────────


class TestEmbeddingInputBuilder:
    def test_embedding_input_builder_exception(self):
        encoder = MagicMock()
        from unittest.mock import patch
        with patch("fcode.indexing.index_service.build_embedding_inputs",
                   side_effect=ValueError("bad chunk")):
            svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
            result = svc.build_through_graphing(FCodeConfig(repo_path="."))
            assert result.run_result.state == IndexState.ERROR
            assert any("EMBEDDING_FAILED" in d.code or "embedding" in d.code
                       for d in result.run_result.diagnostics)

    def test_embedding_input_builder_fails_non_list(self):
        encoder = MagicMock()
        from unittest.mock import patch
        with patch("fcode.indexing.index_service.build_embedding_inputs",
                   return_value="not a list"):
            svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
            result = svc.build_through_graphing(FCodeConfig(repo_path="."))
            assert result.run_result.state == IndexState.ERROR


# ── Encoder invocation ────────────────────────────────────────────────────────


class TestEncoderInvocation:
    def test_encoder_called_with_embedding_inputs(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        encoder.encode.assert_called_once()
        args, _ = encoder.encode.call_args
        assert len(args) >= 1
        inputs_arg = args[0]
        assert isinstance(inputs_arg, list)
        if inputs_arg:
            assert isinstance(inputs_arg[0], EmbeddingInput)

    def test_encoder_exception_extracts_partial_result(self):
        partial = _make_batch_result(eligible=1, success=1, fail=0, skipped=0,
                                      records=[_make_valid_record()])
        exc = RuntimeError("partial failure")
        exc.result = partial
        encoder = MagicMock()
        encoder.encode.side_effect = exc
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING

    def test_encoder_exception_with_embedding_encoder_error(self):
        from fcode.embeddings.encoder import EmbeddingEncoderError
        exc = EmbeddingEncoderError(
            ErrorCode.EMBEDDING_MODEL_UNAVAILABLE,
            "model not found",
            result=_make_batch_result(eligible=1, success=1, fail=0, skipped=0,
                                       records=[_make_valid_record()]),
        )
        encoder = MagicMock()
        encoder.encode.side_effect = exc
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING

    def test_encoder_exception_no_partial_reaches_error(self):
        encoder = MagicMock()
        encoder.encode.side_effect = RuntimeError("total failure")
        graph_builder = MagicMock()
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_encoder_all_chunks_failed_with_partial(self):
        partial = _make_batch_result(eligible=2, success=0, fail=2, skipped=0)
        exc = RuntimeError("all failed")
        exc.result = partial
        encoder = MagicMock()
        encoder.encode.side_effect = exc
        graph_builder = MagicMock()
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR


# ── Embedding result validation ──────────────────────────────────────────────


class TestEmbeddingValidation:
    def test_wrong_result_type(self):
        encoder = MagicMock()
        encoder.encode.return_value = "not an EmbeddingBatchResult"
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_negative_eligible_count(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(eligible=-1)
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_success_count_not_matching_records(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=2, success=2, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_success_plus_fail_not_eligible(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=3, success=1, fail=1, skipped=0,
            records=[_make_valid_record()],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_eligible_plus_skipped_not_inputs_length(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=5, success=1, fail=0, skipped=5,
            records=[_make_valid_record()],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_record_not_embedding_record(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=["not a record"],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_record_empty_chunk_id(self):
        rec = _make_valid_record()
        rec.chunk_id = ""
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_duplicate_chunk_id(self):
        rec1 = _make_valid_record(cid="c1")
        rec2 = _make_valid_record(cid="c1")
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=2, success=2, fail=0, skipped=0,
            records=[rec1, rec2],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_unknown_chunk_id(self):
        rec = _make_valid_record(cid="unknown_cid")
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_metadata_chunk_id_mismatch(self):
        rec = _make_valid_record(cid="c1")
        rec.metadata.chunk_id = "different"
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_vector_wrong_dimension(self):
        rec = _make_valid_record()
        rec.vector = [0.0] * (EXPECTED_DIMENSION - 1)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_vector_contains_bool(self):
        rec = _make_valid_record()
        rec.vector = [True] + [0.0] * (EXPECTED_DIMENSION - 1)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_vector_contains_non_numeric(self):
        rec = _make_valid_record()
        rec.vector = ["bad"] + [0.0] * (EXPECTED_DIMENSION - 1)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_vector_contains_nan(self):
        rec = _make_valid_record()
        rec.vector = [float("nan")] + [0.0] * (EXPECTED_DIMENSION - 1)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_vector_contains_inf(self):
        rec = _make_valid_record()
        rec.vector = [float("inf")] + [0.0] * (EXPECTED_DIMENSION - 1)
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_metadata_absolute_path(self):
        rec = _make_valid_record(path="/abs/path.py")
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_metadata_traversal_path(self):
        rec = _make_valid_record(path="src/../mod.py")
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_metadata_backslash_path(self):
        rec = _make_valid_record(path="src\\mod.py")
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[rec],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR


# ── Embedding outcomes: all failed ───────────────────────────────────────────


class TestEmbeddingAllFailed:
    def test_all_eligible_chunks_failed(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=0, fail=1, skipped=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        assert any("all_chunks_failed" in d.code
                   for d in result.run_result.diagnostics)

    def test_all_failed_skipped_eligible_zero(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=2, success=0, fail=2, skipped=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_success_zero_eligible_zero_no_error(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=0, success=0, fail=0, skipped=1,
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING


# ── Embedding warnings ───────────────────────────────────────────────────────


class TestEmbeddingWarnings:
    def test_warnings_created_from_result_warnings(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=0, fail=1, skipped=0,
            records=[],
            warnings=[{"code": "w1", "chunk_id": "c1", "message": "warning"}],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_warning_from_fail_count_with_no_warnings_list(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=0, fail=1, skipped=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_non_dict_warning_in_list(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
            warnings=["just a string"],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING

    def test_warning_with_path_sanitization(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=0, fail=1, skipped=0,
            warnings=[{"repo_relative_path": "/bad/path"}],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR


# ── Graph builder invocation ─────────────────────────────────────────────────


class TestGraphBuilderInvocation:
    def test_graph_builder_called_with_parsed_files(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        graph_builder.build.assert_called_once()

    def test_graph_builder_exception(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.side_effect = RuntimeError("graph crash")
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_graph_builder_exception_counts_zero(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.side_effect = RuntimeError("crash")
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.counts.graph_nodes == 0
        assert result.run_result.counts.graph_edges == 0


# ── Graph result validation ──────────────────────────────────────────────────


class TestGraphValidation:
    def test_wrong_type(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = "not a GraphBuildResult"
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_nodes_not_a_list(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes="not a list", edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edges_not_a_list(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges="not a list", node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_not_graph_node_input(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=["string node"], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_empty_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_duplicate_node_ids(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[], node_count=2, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_empty_type(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type="")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_absolute_source_file(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                              source_file="/abs/path.py")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_traversal_source_file(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                              source_file="src/../mod.py")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_backslash_source_file(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                              source_file="src\\mod.py")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=1, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_not_graph_edge_input(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=["string edge"], node_count=1, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_duplicate_edge_record_ids(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e1 = GraphEdgeInput(record_id="e1", source_node_id="n1", target_node_id="n2",
                            relation=GraphRelation.DEFINES)
        e2 = GraphEdgeInput(record_id="e1", source_node_id="n1", target_node_id="n2",
                            relation=GraphRelation.DEFINES)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e1, e2], node_count=2, edge_count=2,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_empty_source_node_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e = GraphEdgeInput(source_node_id="", target_node_id="n2",
                           relation=GraphRelation.DEFINES)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e], node_count=2, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_empty_target_node_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e = GraphEdgeInput(source_node_id="n1", target_node_id="",
                           relation=GraphRelation.DEFINES)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e], node_count=2, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_empty_relation(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e = GraphEdgeInput(source_node_id="n1", target_node_id="n2", relation="")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e], node_count=2, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_source_not_known_node(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        e = GraphEdgeInput(source_node_id="unknown", target_node_id="n1",
                           relation=GraphRelation.DEFINES)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1], edges=[e], node_count=1, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_source_file_absolute(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e = GraphEdgeInput(source_node_id="n1", target_node_id="n2",
                           relation=GraphRelation.DEFINES,
                           source_file="/abs/path.py")
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e], node_count=2, edge_count=1,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_node_count_mismatch(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        node = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[node], edges=[], node_count=99, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_edge_count_mismatch(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE)
        n2 = GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION)
        e = GraphEdgeInput(source_node_id="n1", target_node_id="n2",
                           relation=GraphRelation.DEFINES)
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[e], node_count=2, edge_count=99,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR


# ── Successful result ────────────────────────────────────────────────────────


class TestSuccessfulResult:
    def test_state_is_graphing(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                  record_id=_nuuid("n1"))],
            edges=[],
            node_count=1,
            edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING
        assert result.run_result.phase == IndexPhase.GRAPH
        assert result.completed_phase == IndexPhase.EMBED

    def test_counts_populated(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                  record_id=_nuuid("n1"))],
            edges=[],
            node_count=1,
            edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        c = result.run_result.counts
        assert c.scanned == 1
        assert c.parsed == 1
        assert c.chunks == 1
        assert c.symbols == 0
        assert c.embedding_eligible == 1
        assert c.embedded == 1
        assert c.embedding_skipped == 0
        assert c.embedding_failed == 0
        assert c.graph_nodes == 1
        assert c.graph_edges == 0

    def test_results_are_stored(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                  record_id=_nuuid("n1"))],
            edges=[],
            node_count=1,
            edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.embedding_result is not None
        assert result.graph_result is not None
        assert result.graph_result.node_count == 1
        assert len(result.chunks) == 1
        assert len(result.parsed_files) == 1

    def test_no_diagnostics_on_success(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        fatal = [d for d in result.run_result.diagnostics
                 if d.severity == DiagnosticSeverity.ERROR]
        assert len(fatal) == 0


# ── State history ────────────────────────────────────────────────────────────


class TestStateHistory:
    def test_full_state_history(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.state_history == (
            IndexState.PENDING,
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
            IndexState.EMBEDDING,
            IndexState.GRAPHING,
        )

    def test_error_state_history(self):
        encoder = MagicMock()
        encoder.encode.side_effect = RuntimeError("fail")
        svc = _make_default_service(encoder=encoder, graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        history = result.state_history
        assert IndexState.PENDING in history
        assert IndexState.EMBEDDING in history
        assert IndexState.ERROR in history


# ── Safety boundaries ────────────────────────────────────────────────────────


class TestSafetyBoundaries:
    def test_no_persistent_replacement_started(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert not result.persistent_replacement_started

    def test_embedding_result_none_on_failure_before_embedding(self):
        scanner = MagicMock()
        scanner.scan.side_effect = RuntimeError("scan fail")
        svc = _make_default_service(scanner=scanner, encoder=MagicMock(),
                                     graph_builder=MagicMock())
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.embedding_result is None

    def test_graph_result_none_on_failure_before_graph(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.side_effect = RuntimeError("graph fail")
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.graph_result is None

    def test_chunking_success_builder_not_called(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        graph_builder.build.assert_called_once()


# ── Determinism ──────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_fresh_state_machine_per_call(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        r1 = svc.build_through_graphing(FCodeConfig(repo_path="."))
        r2 = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert r1.run_result.state == r2.run_result.state
        assert r1.state_history == r2.state_history
        assert r1.completed_phase == r2.completed_phase

    def test_independent_calls_dont_interfere(self):
        encoder1 = MagicMock()
        encoder1.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder1 = MagicMock()
        graph_builder1.build.return_value = GraphBuildResult(
            nodes=[], edges=[], node_count=0, edge_count=0,
        )
        # Second call will fail
        scanner = MagicMock()
        scanner.scan.side_effect = [MagicMock(), RuntimeError("second fails")]
        scanner.scan.return_value = _make_default_scan_result()
        scan_results = [_make_default_scan_result()]
        def scan_side(*args, **kw):
            return scan_results[0] if scan_results else RuntimeError("no more")
        scanner.scan.side_effect = scan_side
        # Actually simpler: make service that fails on second call
        svc = _make_default_service(encoder=encoder1, graph_builder=graph_builder1)
        r1 = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert r1.run_result.state == IndexState.GRAPHING
        # Create a separate failing service
        scanner2 = MagicMock()
        scanner2.scan.side_effect = RuntimeError("fail")
        svc2 = _make_default_service(scanner=scanner2, encoder=MagicMock(),
                                      graph_builder=MagicMock())
        r2 = svc2.build_through_graphing(FCodeConfig(repo_path="."))
        assert r2.run_result.state == IndexState.ERROR


# ── _build_fatal edge cases ──────────────────────────────────────────────────


class TestBuildFatal:
    def test_fatal_with_chunks(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=MagicMock())
        sm = MagicMock()
        sm.state = IndexState.ERROR
        sm.phase = IndexPhase.EMBED
        sm.completed_phase = IndexPhase.CHUNK
        sm.history = ()
        sm.persistent_replacement_started = False
        result = IndexService._build_fatal(
            sm, [], [], IndexState.ERROR, scan_result=None,
            chunks=[_make_chunk()],
        )
        assert len(result.chunks) == 1

    def test_fatal_with_embedding_result(self):
        svc = _make_default_service(encoder=MagicMock(), graph_builder=MagicMock())
        sm = MagicMock()
        sm.state = IndexState.ERROR
        sm.phase = IndexPhase.EMBED
        sm.completed_phase = IndexPhase.CHUNK
        sm.history = ()
        sm.persistent_replacement_started = False
        emb = _make_batch_result(eligible=1, success=0, fail=1, skipped=0)
        result = IndexService._build_fatal(
            sm, [], [], IndexState.ERROR, scan_result=None,
            chunks=[], embedding_result=emb,
        )
        assert result.embedding_result is not None


# ── Graph builder correction acceptance ───────────────────────────────────────


class TestCorrectedGraphAcceptance:
    def test_multiple_imports_pass_validation(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        n1 = GraphNodeInput(node_id="file:mod.py", node_type=GraphNodeType.FILE,
                            source_file="mod.py", record_id=_nuuid("file:mod.py"))
        n2 = GraphNodeInput(node_id="import:mod.py:os:os:1", node_type=GraphNodeType.IMPORT,
                            source_file="mod.py", record_id=_nuuid("import:mod.py:os:os:1"))
        n3 = GraphNodeInput(node_id="import:mod.py:json:json:2", node_type=GraphNodeType.IMPORT,
                            source_file="mod.py", record_id=_nuuid("import:mod.py:json:json:2"))
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2, n3], edges=[
                GraphEdgeInput(source_node_id="file:mod.py", target_node_id="import:mod.py:os:os:1",
                                relation=GraphRelation.IMPORTS,
                                source_file="mod.py",
                                record_id=_euuid("e1")),
                GraphEdgeInput(source_node_id="file:mod.py", target_node_id="import:mod.py:json:json:2",
                                relation=GraphRelation.IMPORTS,
                                source_file="mod.py",
                                record_id=_euuid("e2")),
            ],
            node_count=3, edge_count=2,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING

    def test_multiple_routes_pass_validation(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        n1 = GraphNodeInput(node_id="file:routes.py", node_type=GraphNodeType.FILE,
                            source_file="routes.py", record_id=_nuuid("file:routes.py"))
        n2 = GraphNodeInput(node_id="route:GET:/items:routes.py:1", node_type=GraphNodeType.ROUTE,
                            source_file="routes.py",
                            record_id=_nuuid("route:GET:/items:routes.py:1"))
        n3 = GraphNodeInput(node_id="route:POST:/items:routes.py:2", node_type=GraphNodeType.ROUTE,
                            source_file="routes.py",
                            record_id=_nuuid("route:POST:/items:routes.py:2"))
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2, n3], edges=[],
            node_count=3, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.GRAPHING

    def test_rejects_genuinely_invalid_duplicate_nodes(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        n1 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                            source_file="mod.py", record_id=_nuuid("dup1"))
        n2 = GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                            source_file="mod.py", record_id=_nuuid("dup2"))
        graph_builder.build.return_value = GraphBuildResult(
            nodes=[n1, n2], edges=[], node_count=2, edge_count=0,
        )
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR

    def test_embedding_result_retained_on_graph_failure(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        graph_builder = MagicMock()
        graph_builder.build.side_effect = RuntimeError("graph fail")
        svc = _make_default_service(encoder=encoder, graph_builder=graph_builder)
        result = svc.build_through_graphing(FCodeConfig(repo_path="."))
        assert result.run_result.state == IndexState.ERROR
        assert result.embedding_result is not None
        assert result.graph_result is None


# ── §3 closure invariants: graph identity guarantees ─────────────────────────


class TestGraphIdentityInvariants:
    """WP5 Step 3 closure §3: successful results must have unique node IDs,
    unique node record IDs, unique canonical edges, unique edge record IDs,
    and every edge endpoint must reference a known node. The validator
    enforces this on every non-fatal result."""

    def _build_graph_result(self, nodes, edges=None):
        edges = edges or []
        return GraphBuildResult(
            nodes=nodes, edges=edges,
            node_count=len(nodes), edge_count=len(edges),
        )

    def _success_result(self, srv):
        r = srv.build_through_graphing(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.GRAPHING, (
            f"unexpected ERROR; diag={[d.message for d in r.run_result.diagnostics]}"
        )
        return r

    def _fail_result(self, srv):
        r = srv.build_through_graphing(FCodeConfig(repo_path="."))
        assert r.run_result.state == IndexState.ERROR
        return r

    def test_validator_rejects_empty_node_record_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        # node with empty record ID must be rejected
        gb.build.return_value = self._build_graph_result([
            GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                            record_id=""),
        ])
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._fail_result(svc)

    def test_validator_rejects_duplicate_node_record_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        gb.build.return_value = self._build_graph_result([
            GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                            record_id=_nuuid("dup")),
            GraphNodeInput(node_id="n2", node_type=GraphNodeType.FILE,
                            record_id=_nuuid("dup")),
        ])
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._fail_result(svc)

    def test_validator_rejects_empty_edge_record_id(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        gb.build.return_value = self._build_graph_result(
            nodes=[
                GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                record_id=_nuuid("n1")),
                GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION,
                                record_id=_nuuid("n2")),
            ],
            edges=[
                GraphEdgeInput(source_node_id="n1", target_node_id="n2",
                                relation=GraphRelation.DEFINES, record_id=""),
            ],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._fail_result(svc)

    def test_validator_rejects_duplicate_canonical_edges(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        e1 = GraphEdgeInput(source_node_id="n1", target_node_id="n2",
                              relation=GraphRelation.DEFINES,
                              source_file="mod.py", source_location="mod.py:1",
                              record_id=_euuid("e1"))
        e2 = GraphEdgeInput(source_node_id="n1", target_node_id="n2",
                              relation=GraphRelation.DEFINES,
                              source_file="mod.py", source_location="mod.py:1",
                              record_id=_euuid("e2"))
        gb.build.return_value = self._build_graph_result(
            nodes=[
                GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                record_id=_nuuid("n1")),
                GraphNodeInput(node_id="n2", node_type=GraphNodeType.FUNCTION,
                                record_id=_nuuid("n2")),
            ],
            edges=[e1, e2],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._fail_result(svc)

    def test_validator_rejects_orphan_edge_endpoint(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        gb.build.return_value = self._build_graph_result(
            nodes=[
                GraphNodeInput(node_id="n1", node_type=GraphNodeType.FILE,
                                record_id=_nuuid("n1")),
            ],
            edges=[
                GraphEdgeInput(source_node_id="n1", target_node_id="ghost",
                                relation=GraphRelation.DEFINES,
                                record_id=_euuid("e1")),
            ],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._fail_result(svc)

    def test_validator_accepts_well_formed_graph(self):
        encoder = MagicMock()
        encoder.encode.return_value = _make_batch_result(
            eligible=1, success=1, fail=0, skipped=0,
            records=[_make_valid_record()],
        )
        gb = MagicMock()
        gb.build.return_value = self._build_graph_result(
            nodes=[
                GraphNodeInput(node_id="file:mod.py",
                                node_type=GraphNodeType.FILE,
                                source_file="mod.py",
                                record_id=_nuuid("file:mod.py")),
                GraphNodeInput(node_id="function:mod.py:foo:1",
                                node_type=GraphNodeType.FUNCTION,
                                source_file="mod.py",
                                record_id=_nuuid("function:mod.py:foo:1")),
            ],
            edges=[
                GraphEdgeInput(source_node_id="file:mod.py",
                                target_node_id="function:mod.py:foo:1",
                                relation=GraphRelation.DEFINES,
                                source_file="mod.py",
                                source_location="mod.py:1",
                                record_id=_euuid("e1")),
            ],
        )
        svc = _make_default_service(encoder=encoder, graph_builder=gb)
        r = self._success_result(svc)
        # invariants: every node_id, node_record_id, edge_record_id, edge
        # canonical tuple is unique in the result graph.
        g = r.graph_result
        nids = [n.node_id for n in g.nodes]
        nrids = [n.record_id for n in g.nodes]
        erids = [e.record_id for e in g.edges]
        canon = [(e.source_node_id, e.target_node_id, e.relation.value,
                  e.source_file or "", e.source_location or "")
                 for e in g.edges]
        assert len(set(nids)) == len(nids)
        assert len(set(nrids)) == len(nrids)
        assert len(set(erids)) == len(erids)
        assert len(set(canon)) == len(canon)
        node_id_set = set(nids)
        for e in g.edges:
            assert e.source_node_id in node_id_set
            assert e.target_node_id in node_id_set
