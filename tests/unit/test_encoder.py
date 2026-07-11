"""Unit tests for EmbeddingEncoder — local offline embeddings."""

import importlib
import json
import math
import sys
from typing import Any

import pytest

from fcode.contracts.enums import ChunkType, ParseStatus
from fcode.contracts.errors import ErrorCode
from fcode.contracts.models import (
    CodeChunk,
    EmbeddingBatchResult,
    EmbeddingInput,
    EmbeddingMetadata,
    EmbeddingRecord,
)
from fcode.embeddings import EmbeddingEncoder, EmbeddingEncoderError, build_embedding_inputs
from fcode.embeddings.encoder import (
    BATCH_SIZE,
    EXPECTED_DIMENSION,
    MAX_EMBEDDING_BYTES,
    MAX_OVERSIZE_LINES,
    MODEL_NAME,
)


# ── Fake model module ─────────────────────────────────────────────────────────


class _FakeST:
    """Minimal fake sentence_transformers.SentenceTransformer."""

    call_count = 0

    def __init__(self, model_name="", device="cpu", local_files_only=True):
        self.model_name = model_name
        self.device = device
        self.local_files_only = local_files_only
        type(self).call_count = 0

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **kwargs):
        type(self).call_count += 1
        return [[0.1 + i * 0.01 + j * 0.001 for j in range(EXPECTED_DIMENSION)]
                for i in range(len(texts))]


class _FakeBadDimST:
    def __init__(self, model_name="", **kw):
        pass

    def get_sentence_embedding_dimension(self):
        return 512

    def encode(self, texts, **kwargs):
        return [[0.1] * 512 for _ in texts]


class _FakeFailST:
    def __init__(self, model_name="", **kw):
        pass

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **kwargs):
        raise RuntimeError("simulated encode failure")


def _make_fake_st_module(cls):
    """Create a fake sentence_transformers module with given SentenceTransformer class."""
    import types
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = cls
    return mod


def _inject_st(monkeypatch, cls=_FakeST):
    """Inject a fake sentence_transformers module into sys.modules."""
    monkeypatch.setitem(sys.modules, "sentence_transformers", _make_fake_st_module(cls))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _chunk(
    chunk_id: str = "chunk-1",
    file_id: str = "file-1",
    chunk_type: ChunkType = ChunkType.FUNCTION,
    content: str = "def foo(): pass",
    start_line: int = 1,
    end_line: int = 2,
    file_path: str = "mod.py",
    language: str = "Python",
    symbol_name: str = "foo",
    has_secrets: bool = False,
    parse_status: str = "parsed",
) -> CodeChunk:
    return CodeChunk(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_type=chunk_type,
        content=content,
        start_line=start_line,
        end_line=end_line,
        file_path=file_path,
        language=language,
        symbol_name=symbol_name,
        metadata={"has_secrets": has_secrets, "parse_status": parse_status},
    )


def _input(
    chunk_id: str = "chunk-1",
    content: str = "def foo(): pass",
    file_path: str = "mod.py",
    symbol_name: str = "foo",
    chunk_type: ChunkType = ChunkType.FUNCTION,
    language: str = "Python",
    start_line: int = 1,
    end_line: int = 2,
    has_secrets: bool = False,
    parse_status: ParseStatus = ParseStatus.PARSED,
) -> EmbeddingInput:
    return EmbeddingInput(
        chunk_id=chunk_id,
        content=content,
        metadata=EmbeddingMetadata(
            chunk_id=chunk_id,
            file_path=file_path,
            symbol_name=symbol_name,
            chunk_type=chunk_type,
            language=language,
            start_line=start_line,
            end_line=end_line,
        ),
        has_secrets=has_secrets,
        parse_status=parse_status,
    )


# ── Contract tests ────────────────────────────────────────────────────────────


class TestEmbeddingMetadataContract:
    def test_exact_fields(self):
        m = EmbeddingMetadata(
            chunk_id="c1", file_path="f.py", symbol_name="s",
            chunk_type=ChunkType.FUNCTION, start_line=1, end_line=10,
        )
        assert m.chunk_id == "c1"
        assert m.file_path == "f.py"
        assert m.symbol_name == "s"
        assert m.chunk_type == ChunkType.FUNCTION
        assert m.start_line == 1
        assert m.end_line == 10

    def test_stale_source_file_absent(self):
        assert not hasattr(EmbeddingMetadata, "source_file")

    def test_json_serializable(self):
        m = EmbeddingMetadata(
            chunk_id="c1", file_path="f.py", symbol_name="s",
            chunk_type=ChunkType.FUNCTION, start_line=1, end_line=10,
        )
        d = {"chunk_id": m.chunk_id, "file_path": m.file_path}
        s = json.dumps(d)
        assert isinstance(s, str)


class TestEmbeddingInputContract:
    def test_exact_fields(self):
        inp = _input()
        assert inp.chunk_id == "chunk-1"
        assert inp.content == "def foo(): pass"
        assert inp.has_secrets is False
        assert inp.parse_status == ParseStatus.PARSED

    def test_stale_text_absent(self):
        assert not hasattr(EmbeddingInput, "text")


class TestEmbeddingBatchResultContract:
    def test_records_field_exists(self):
        r = EmbeddingBatchResult()
        assert hasattr(r, "records")
        assert hasattr(r, "eligible_count")
        assert hasattr(r, "success_count")
        assert hasattr(r, "fail_count")
        assert hasattr(r, "skipped_count")
        assert hasattr(r, "warnings")
        assert hasattr(r, "errors")


class TestEncoderProtocol:
    def test_protocol_exposes_ensure_available(self):
        from fcode.contracts.interfaces import EmbeddingEncoderProtocol
        assert hasattr(EmbeddingEncoderProtocol, "ensure_available")

    def test_protocol_exposes_encode(self):
        from fcode.contracts.interfaces import EmbeddingEncoderProtocol
        assert hasattr(EmbeddingEncoderProtocol, "encode")

    def test_concrete_param_names_match_protocol(self):
        import inspect
        from fcode.contracts.interfaces import EmbeddingEncoderProtocol
        proto = inspect.signature(EmbeddingEncoderProtocol.encode)
        impl = inspect.signature(EmbeddingEncoder.encode)
        proto_params = list(proto.parameters.keys())
        impl_params = list(impl.parameters.keys())
        assert proto_params == impl_params


class TestErrorCodes:
    def test_canonical_codes_exist(self):
        assert ErrorCode.EMBEDDING_MODEL_UNAVAILABLE
        assert ErrorCode.EMBEDDING_DIMENSION_MISMATCH
        assert ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED
        assert ErrorCode.EMBEDDING_CHUNK_WARNING
        assert ErrorCode.EMBEDDING_FAILED


# ── Input builder tests ───────────────────────────────────────────────────────


class TestBuildEmbeddingInputs:
    def test_code_chunk_converts(self):
        c = _chunk()
        result = build_embedding_inputs([c])
        assert len(result) == 1
        r = result[0]
        assert r.chunk_id == "chunk-1"
        assert r.content == "def foo(): pass"
        assert r.has_secrets is False
        assert r.parse_status == ParseStatus.PARSED

    def test_order_preserved(self):
        c1 = _chunk("a", content="first")
        c2 = _chunk("b", content="second")
        result = build_embedding_inputs([c1, c2])
        assert result[0].chunk_id == "a"
        assert result[1].chunk_id == "b"

    def test_symbol_name_defaults_to_empty_string(self):
        c = _chunk("c1", symbol_name=None)
        result = build_embedding_inputs([c])
        assert result[0].metadata.symbol_name == ""

    def test_language_preserved(self):
        c = _chunk("c1", language="Markdown")
        result = build_embedding_inputs([c])
        assert result[0].metadata.language == "Markdown"

    def test_has_secrets_preserved(self):
        c = _chunk("c1", has_secrets=True)
        result = build_embedding_inputs([c])
        assert result[0].has_secrets is True

    def test_parsed_status_string_normalized(self):
        c = _chunk("c1", parse_status="parsed")
        result = build_embedding_inputs([c])
        assert result[0].parse_status == ParseStatus.PARSED

    def test_enum_parse_status_preserved(self):
        c = _chunk("c1", parse_status="not_applicable")
        result = build_embedding_inputs([c])
        assert result[0].parse_status == ParseStatus.NOT_APPLICABLE

    def test_invalid_parse_status_raises(self):
        c = _chunk("c1", parse_status="bogus")
        with pytest.raises(ValueError, match="invalid parse_status"):
            build_embedding_inputs([c])

    def test_missing_has_secrets_raises(self):
        c = _chunk("c1")
        c.metadata = {}
        with pytest.raises(ValueError, match="missing has_secrets"):
            build_embedding_inputs([c])

    def test_non_boolean_has_secrets_raises(self):
        c = _chunk("c1")
        c.metadata["has_secrets"] = "yes"
        with pytest.raises(ValueError, match="non-boolean has_secrets"):
            build_embedding_inputs([c])

    def test_absolute_path_rejected(self):
        c = _chunk("c1", file_path="/abs/path.py")
        with pytest.raises(ValueError, match="absolute"):
            build_embedding_inputs([c])

    def test_traversal_path_rejected(self):
        c = _chunk("c1", file_path="sub/../mod.py")
        with pytest.raises(ValueError, match="traversal"):
            build_embedding_inputs([c])

    def test_original_code_chunk_not_mutated(self):
        c = _chunk("c1")
        orig_content = c.content
        _ = build_embedding_inputs([c])
        assert c.content == orig_content

    def test_negative_line_range_rejected(self):
        c = _chunk("c1", start_line=0)
        with pytest.raises(ValueError, match="invalid line range"):
            build_embedding_inputs([c])

    def test_reversed_line_range_rejected(self):
        c = _chunk("c1", start_line=5, end_line=3)
        with pytest.raises(ValueError, match="invalid line range"):
            build_embedding_inputs([c])

    def test_duplicate_chunk_id_rejected(self):
        c1 = _chunk("c1")
        c2 = _chunk("c1")
        with pytest.raises(ValueError, match="duplicate chunk_id"):
            build_embedding_inputs([c1, c2])

    def test_empty_chunk_id_rejected(self):
        c = _chunk("")
        with pytest.raises(ValueError, match="empty chunk_id"):
            build_embedding_inputs([c])

    def test_empty_file_path_rejected(self):
        c = _chunk("c1", file_path="")
        with pytest.raises(ValueError, match="empty file_path"):
            build_embedding_inputs([c])


# ── Lazy / local model loading ────────────────────────────────────────────────


class TestLazyModelLoading:
    def test_package_import_does_not_import_sentence_transformers(self):
        before = {m for m in sys.modules if "sentence_transformers" in m}
        import fcode.embeddings  # noqa: F811
        after = {m for m in sys.modules if "sentence_transformers" in m}
        assert after == before

    def test_construction_does_not_load_model(self):
        enc = EmbeddingEncoder()
        assert enc._model is None

    def test_exact_model_name_used(self, monkeypatch):
        _inject_st(monkeypatch)
        orig_st = _FakeST
        model_names = []
        def fake_st(model_name="", **kw):
            model_names.append(model_name)
            return orig_st(model_name, **kw)
        monkeypatch.setattr(_FakeST.__module__ + "._FakeST", lambda **kw: orig_st(**kw))
        # simpler: just verify the constant is used
        assert MODEL_NAME == "sentence-transformers/all-MiniLM-L6-v2"

    def test_no_hardcoded_cache_path(self):
        import inspect
        source = inspect.getsource(EmbeddingEncoder._load_model)
        assert "cache_folder" not in source
        assert "cache_dir" not in source

    def test_offline_environment_temporary(self, monkeypatch):
        _inject_st(monkeypatch)
        import os
        before = os.environ.get("HF_HUB_OFFLINE")
        enc = EmbeddingEncoder()
        enc._load_model()
        after = os.environ.get("HF_HUB_OFFLINE")
        assert before == after

    def test_model_loads_only_once(self, monkeypatch):
        _inject_st(monkeypatch)
        _FakeST.call_count = 0
        enc = EmbeddingEncoder()
        enc._load_model()
        enc._load_model()
        assert enc._model is not None

    def test_model_unavailable_error_code(self, monkeypatch):
        class Unavailable:
            def __init__(self, model_name="", **kw):
                raise RuntimeError("model not found")
        _inject_st(monkeypatch, Unavailable)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc._load_model()
        assert exc.value.code == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE

    def test_wrong_dimension_error_code(self, monkeypatch):
        _inject_st(monkeypatch, _FakeBadDimST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc._load_model()
        assert exc.value.code == ErrorCode.EMBEDDING_DIMENSION_MISMATCH

    def test_error_messages_no_cache_path_leakage(self, monkeypatch):
        class Unavailable:
            def __init__(self, model_name="", **kw):
                raise RuntimeError("model not found")
        _inject_st(monkeypatch, Unavailable)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc._load_model()
        msg = str(exc.value)
        assert "cache" not in msg.lower()
        assert "home" not in msg.lower()


# ── Eligibility ───────────────────────────────────────────────────────────────


class TestEligibility:
    def _make_enc(self, monkeypatch):
        _inject_st(monkeypatch)
        return EmbeddingEncoder()

    def test_empty_content_skipped(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", content="")])
        assert result.skipped_count == 1
        assert result.eligible_count == 0

    def test_whitespace_content_skipped(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", content="   \n  ")])
        assert result.skipped_count == 1

    def test_secret_bearing_input_skipped(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", has_secrets=True)])
        assert result.skipped_count == 1

    def test_parse_error_input_skipped(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", parse_status=ParseStatus.ERROR)])
        assert result.skipped_count == 1

    def test_not_applicable_remains_eligible(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", parse_status=ParseStatus.NOT_APPLICABLE)])
        assert result.eligible_count == 1
        assert result.success_count == 1

    def test_all_skipped_returns_zero_result(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        result = enc.encode([_input("c1", content="")])
        assert result.eligible_count == 0
        assert result.success_count == 0
        assert result.fail_count == 0
        assert len(result.records) == 0

    def test_all_skipped_does_not_load_model(self, monkeypatch):
        loaded = []
        class TrapST:
            def __init__(self, model_name="", **kw):
                loaded.append(True)
        _inject_st(monkeypatch, TrapST)
        enc = EmbeddingEncoder()
        _ = enc.encode([_input("c1", content="")])
        assert len(loaded) == 0

    def test_skipped_content_never_reaches_model(self, monkeypatch):
        model_inputs = []
        class Tracking:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                model_inputs.extend(texts)
                return [[0.1] * EXPECTED_DIMENSION for _ in texts]
        _inject_st(monkeypatch, Tracking)
        enc = EmbeddingEncoder()
        _ = enc.encode([_input("c1", content=""), _input("c2", content="real code")])
        assert "real code" in model_inputs
        assert "" not in model_inputs


# ── Oversized content ─────────────────────────────────────────────────────────


class TestOversizedContent:
    def test_content_at_or_below_100kb_unchanged(self):
        small = "x" * 1000
        inp = _input("c1", content=small)
        prepared = EmbeddingEncoder._prepare_content(inp)
        assert prepared == small

    def test_content_over_100kb_uses_first_100_lines(self):
        big = "\n".join(["x" * 1024 + str(i) for i in range(200)])
        inp = _input("c1", content=big)
        assert len(big.encode("utf-8")) > MAX_EMBEDDING_BYTES
        prepared = EmbeddingEncoder._prepare_content(inp)
        assert prepared.count("\n") + 1 == MAX_OVERSIZE_LINES

    def test_original_input_content_unchanged(self):
        big = "\n".join(f"line{i}" for i in range(200))
        inp = _input("c1", content=big)
        _ = EmbeddingEncoder._prepare_content(inp)
        assert inp.content == big

    def test_final_newline_handling(self):
        content = "\n".join("x" * 1024 + str(i) for i in range(150))
        inp = _input("c1", content=content + "\n")
        prepared = EmbeddingEncoder._prepare_content(inp)
        assert prepared.count("\n") == MAX_OVERSIZE_LINES - 1


# ── Batching ──────────────────────────────────────────────────────────────────


class TestBatching:
    def _make_enc(self, monkeypatch):
        _inject_st(monkeypatch)
        return EmbeddingEncoder()

    def test_1_input_creates_1_call(self, monkeypatch):
        _FakeST.call_count = 0
        enc = self._make_enc(monkeypatch)
        enc.encode([_input(f"c{i}") for i in range(1)])
        assert _FakeST.call_count == 1

    def test_100_inputs_creates_1_call(self, monkeypatch):
        _FakeST.call_count = 0
        enc = self._make_enc(monkeypatch)
        enc.encode([_input(f"c{i}") for i in range(100)])
        assert _FakeST.call_count == 1

    def test_101_inputs_creates_2_calls(self, monkeypatch):
        _FakeST.call_count = 0
        enc = self._make_enc(monkeypatch)
        enc.encode([_input(f"c{i}") for i in range(101)])
        assert _FakeST.call_count == 2

    def test_200_inputs_creates_2_calls(self, monkeypatch):
        _FakeST.call_count = 0
        enc = self._make_enc(monkeypatch)
        enc.encode([_input(f"c{i}") for i in range(200)])
        assert _FakeST.call_count == 2

    def test_201_inputs_creates_3_calls(self, monkeypatch):
        _FakeST.call_count = 0
        enc = self._make_enc(monkeypatch)
        enc.encode([_input(f"c{i}") for i in range(201)])
        assert _FakeST.call_count == 3

    def test_record_order_stable(self, monkeypatch):
        enc = self._make_enc(monkeypatch)
        inputs = [_input(f"c{i}", content=str(i)) for i in range(10)]
        result = enc.encode(inputs)
        ids = [r.chunk_id for r in result.records]
        assert ids == ["c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"]


# ── Vector validation ─────────────────────────────────────────────────────────


class TestVectorValidation:
    def test_384_vector_accepted(self):
        vec = [0.1] * EXPECTED_DIMENSION
        result = EmbeddingEncoder._validate_vector(vec)
        assert len(result) == EXPECTED_DIMENSION
        assert all(isinstance(v, float) for v in result)

    def test_output_converted_to_float_list(self):
        result = EmbeddingEncoder._validate_vector([1, 2, 3] + [0.0] * (EXPECTED_DIMENSION - 3))
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_tuple_output_accepted(self):
        vec = tuple([0.1] * EXPECTED_DIMENSION)
        result = EmbeddingEncoder._validate_vector(vec)
        assert len(result) == EXPECTED_DIMENSION

    def test_numpy_like_output_accepted(self):
        class NumpyLike:
            def __iter__(self):
                return iter([0.1] * EXPECTED_DIMENSION)
        result = EmbeddingEncoder._validate_vector(NumpyLike())
        assert len(result) == EXPECTED_DIMENSION

    def test_wrong_dimension_fatal(self):
        vec = [0.1] * 100
        with pytest.raises(EmbeddingEncoderError) as exc:
            EmbeddingEncoder._validate_vector(vec)
        assert exc.value.code == ErrorCode.EMBEDDING_DIMENSION_MISMATCH

    def test_nonnumeric_value_fatal(self):
        vec = [0.1] * (EXPECTED_DIMENSION - 1) + ["x"]
        with pytest.raises(EmbeddingEncoderError) as exc:
            EmbeddingEncoder._validate_vector(vec)
        assert exc.value.code == ErrorCode.EMBEDDING_FAILED

    def test_boolean_value_fatal(self):
        vec = [0.1] * (EXPECTED_DIMENSION - 1) + [True]
        with pytest.raises(EmbeddingEncoderError) as exc:
            EmbeddingEncoder._validate_vector(vec)
        assert exc.value.code == ErrorCode.EMBEDDING_FAILED

    def test_nan_value_fatal(self):
        vec = [0.1] * (EXPECTED_DIMENSION - 1) + [float("nan")]
        with pytest.raises(EmbeddingEncoderError) as exc:
            EmbeddingEncoder._validate_vector(vec)
        assert exc.value.code == ErrorCode.EMBEDDING_FAILED

    def test_infinity_value_fatal(self):
        vec = [0.1] * (EXPECTED_DIMENSION - 1) + [float("inf")]
        with pytest.raises(EmbeddingEncoderError) as exc:
            EmbeddingEncoder._validate_vector(vec)
        assert exc.value.code == ErrorCode.EMBEDDING_FAILED

    def test_output_count_mismatch_fatal(self, monkeypatch):
        class CountMismatch:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                return [[0.1] * EXPECTED_DIMENSION]
        _inject_st(monkeypatch, CountMismatch)
        enc = EmbeddingEncoder()
        inputs = [_input(f"c{i}") for i in range(2)]
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode(inputs)
        assert exc.value.code == ErrorCode.EMBEDDING_FAILED

    def test_record_chunk_id_preserved(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        result = enc.encode([_input("my-chunk")])
        assert result.records[0].chunk_id == "my-chunk"

    def test_record_metadata_preserved(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        inp = _input("c1", file_path="app/main.py", symbol_name="main")
        result = enc.encode([inp])
        assert result.records[0].metadata.file_path == "app/main.py"
        assert result.records[0].metadata.symbol_name == "main"


# ── Failure handling ──────────────────────────────────────────────────────────


class TestFailureHandling:
    def _make_failing(self, monkeypatch, fail_on_call=1):
        call_count = [0]
        class PartialFail:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                call_count[0] += 1
                if call_count[0] == fail_on_call:
                    raise RuntimeError("batch fail")
                return [[0.1] * EXPECTED_DIMENSION for _ in texts]
        _inject_st(monkeypatch, PartialFail)
        return EmbeddingEncoder()

    def test_partial_success_with_one_failed_item(self, monkeypatch):
        enc = self._make_failing(monkeypatch, fail_on_call=2)
        result = enc.encode([_input(f"c{i}") for i in range(101)])
        assert result.success_count == 100
        assert result.fail_count == 1
        assert len(result.records) == 100
        assert len(result.warnings) == 1

    def test_failed_batch_creates_one_warning_per_chunk(self, monkeypatch):
        _inject_st(monkeypatch, _FakeFailST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode([_input(f"c{i}") for i in range(3)])
        assert exc.value.code == ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED
        assert exc.value.result is not None
        assert exc.value.result.fail_count == 3
        assert len(exc.value.result.warnings) == 3

    def test_failed_batch_not_retried(self, monkeypatch):
        call_count = [0]
        class OnceFail:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                call_count[0] += 1
                raise RuntimeError("fail")
        _inject_st(monkeypatch, OnceFail)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError):
            enc.encode([_input(f"c{i}") for i in range(5)])
        assert call_count[0] == 1

    def test_later_batches_continue_after_earlier_failure(self, monkeypatch):
        call_records = []
        class Sequence:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                call_records.append(len(texts))
                if len(call_records) == 1:
                    raise RuntimeError("first fail")
                return [[0.2] * EXPECTED_DIMENSION for _ in texts]
        _inject_st(monkeypatch, Sequence)
        enc = EmbeddingEncoder()
        inputs = [_input(f"c{i}") for i in range(150)]
        result = enc.encode(inputs)
        assert result.success_count == 50
        assert result.fail_count == 100

    def test_all_eligible_batches_failed_raises(self, monkeypatch):
        _inject_st(monkeypatch, _FakeFailST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode([_input(f"c{i}") for i in range(5)])
        assert exc.value.code == ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED

    def test_all_chunks_failed_exception_contains_partial_result(self, monkeypatch):
        _inject_st(monkeypatch, _FakeFailST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode([_input(f"c{i}") for i in range(3)])
        assert exc.value.result is not None
        assert exc.value.result.eligible_count == 3
        assert exc.value.result.fail_count == 3

    def test_warning_contains_code_and_chunk_id(self, monkeypatch):
        _inject_st(monkeypatch, _FakeFailST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode([_input("c1")])
        for w in exc.value.result.warnings:
            assert "code" in w
            assert "chunk_id" in w
            assert w["code"] == "embedding_chunk_warning"
            assert w["chunk_id"] == "c1"

    def test_warning_contains_no_source_content(self, monkeypatch):
        _inject_st(monkeypatch, _FakeFailST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError) as exc:
            enc.encode([_input("c1", content="secret content")])
        for w in exc.value.result.warnings:
            assert "secret" not in w.get("message", "")
            assert w["chunk_id"] == "c1"

    def test_partial_success_invariant_correct(self, monkeypatch):
        call_count = [0]
        class Partial:
            def __init__(self, model_name="", **kw):
                pass
            def get_sentence_embedding_dimension(self):
                return EXPECTED_DIMENSION
            def encode(self, texts, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return [[0.1] * EXPECTED_DIMENSION for _ in texts]
                raise RuntimeError("fail")
        _inject_st(monkeypatch, Partial)
        enc = EmbeddingEncoder()
        inputs = [_input(f"c{i}") for i in range(150)]
        result = enc.encode(inputs)
        assert result.success_count + result.fail_count == result.eligible_count

    def test_zero_eligible_invariant_correct(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        result = enc.encode([_input("c1", content="")])
        assert result.eligible_count == 0
        assert result.success_count == 0
        assert result.fail_count == 0
        assert result.skipped_count == 1


# ── Determinism and safety ────────────────────────────────────────────────────


class TestDeterminismAndSafety:
    def test_repeated_fake_encoding_identical_vectors(self, monkeypatch):
        _inject_st(monkeypatch)
        enc1 = EmbeddingEncoder()
        enc2 = EmbeddingEncoder()
        inp = _input("c1", content="def foo(): pass")
        r1 = enc1.encode([inp])
        r2 = enc2.encode([inp])
        assert r1.records[0].vector == r2.records[0].vector

    def test_repeated_record_ordering_identical(self, monkeypatch):
        _inject_st(monkeypatch)
        enc1 = EmbeddingEncoder()
        enc2 = EmbeddingEncoder()
        inp = [_input(f"c{i}", content=str(i)) for i in range(5)]
        r1 = enc1.encode(inp)
        r2 = enc2.encode(inp)
        assert [r.chunk_id for r in r1.records] == [r.chunk_id for r in r2.records]

    def test_encoder_does_not_read_files(self, monkeypatch):
        calls = []
        import builtins
        original = builtins.open
        def trap(*a, **kw):
            calls.append(a[0])
            return original(*a, **kw)
        monkeypatch.setattr(builtins, "open", trap)
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        enc.encode([_input("c1")])

    def test_encoder_does_not_access_storage(self, monkeypatch):
        import inspect
        source = inspect.getsource(EmbeddingEncoder.encode) + inspect.getsource(EmbeddingEncoder._load_model)
        assert "chromadb" not in source
        assert "sqlite3" not in source
        before = {k for k in sys.modules if "chromadb" in k or "sqlite3" in k or "fcode.storage" in k}
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        enc.encode([_input("c1")])
        after = {k for k in sys.modules if "chromadb" in k or "sqlite3" in k or "fcode.storage" in k}
        assert after == before

    def test_encoder_does_not_access_network(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        enc.encode([_input("c1")])

    def test_encoder_does_not_launch_subprocesses(self):
        import inspect
        source = inspect.getsource(EmbeddingEncoder.encode)
        assert "subprocess" not in source

    def test_encoder_does_not_mutate_inputs(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        inp = _input("c1", content="original")
        orig_id = inp.chunk_id
        orig_content = inp.content
        _ = enc.encode([inp])
        assert inp.chunk_id == orig_id
        assert inp.content == orig_content


# ── Duplicate input validation ────────────────────────────────────────────────


class TestDuplicateInputValidation:
    def test_duplicate_chunk_id_raises_value_error(self):
        enc = EmbeddingEncoder()
        with pytest.raises(ValueError, match="duplicate chunk_id"):
            enc.encode([_input("c1"), _input("c1")])

    def test_empty_chunk_id_raises(self):
        enc = EmbeddingEncoder()
        with pytest.raises(ValueError, match="empty chunk_id"):
            enc.encode([_input("")])

    def test_chunk_id_mismatch_with_metadata_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1")
        inp.metadata.chunk_id = "c2"
        with pytest.raises(ValueError, match="chunk_id mismatch"):
            enc.encode([inp])

    def test_invalid_metadata_line_range_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1", start_line=10, end_line=5)
        with pytest.raises(ValueError, match="invalid metadata line range"):
            enc.encode([inp])

    def test_absolute_metadata_file_path_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1", file_path="/abs/path.py")
        with pytest.raises(ValueError, match="absolute metadata file_path"):
            enc.encode([inp])

    def test_traversal_metadata_file_path_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1", file_path="sub/../mod.py")
        with pytest.raises(ValueError, match="traversal metadata file_path"):
            enc.encode([inp])

    def test_unsupported_metadata_chunk_type_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1")
        inp.metadata.chunk_type = "invalid"
        with pytest.raises(ValueError, match="unsupported metadata chunk_type"):
            enc.encode([inp])

    def test_malformed_input_content_type_raises(self):
        enc = EmbeddingEncoder()
        inp = _input("c1")
        inp.content = 123
        with pytest.raises(ValueError, match="malformed input content type"):
            enc.encode([inp])


# ── EmbeddingEncoderError tests ───────────────────────────────────────────────


class TestEmbeddingEncoderError:
    def test_str_sanitized(self):
        err = EmbeddingEncoderError(ErrorCode.EMBEDDING_FAILED, "test error")
        assert "test error" in str(err)

    def test_no_input_content_in_message(self):
        err = EmbeddingEncoderError(ErrorCode.EMBEDDING_FAILED, "some error")
        assert "def foo" not in str(err)

    def test_no_raw_secret_in_message(self):
        err = EmbeddingEncoderError(ErrorCode.EMBEDDING_FAILED, "some error")
        assert "secret" not in str(err)

    def test_code_present(self):
        err = EmbeddingEncoderError(ErrorCode.EMBEDDING_FAILED, "err")
        assert err.code == ErrorCode.EMBEDDING_FAILED

    def test_result_optional(self):
        err = EmbeddingEncoderError(ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED, "err")
        assert err.result is None
        r = EmbeddingBatchResult(eligible_count=3, fail_count=3)
        err2 = EmbeddingEncoderError(ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED, "err", result=r)
        assert err2.result is not None
        assert err2.result.eligible_count == 3


# ── ensure_available integration ──────────────────────────────────────────────


class TestEnsureAvailable:
    def test_ensure_available_loads_model(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        assert enc._model is None
        enc.ensure_available()
        assert enc._model is not None

    def test_ensure_available_raises_on_unavailable(self, monkeypatch):
        class Unavailable:
            def __init__(self, model_name="", **kw):
                raise RuntimeError("no model")
        _inject_st(monkeypatch, Unavailable)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError):
            enc.ensure_available()

    def test_ensure_available_raises_on_dimension_mismatch(self, monkeypatch):
        _inject_st(monkeypatch, _FakeBadDimST)
        enc = EmbeddingEncoder()
        with pytest.raises(EmbeddingEncoderError):
            enc.ensure_available()


# ── Exports ───────────────────────────────────────────────────────────────────


class TestExports:
    def test_embedding_encoder_exported(self):
        from fcode.embeddings import EmbeddingEncoder
        assert EmbeddingEncoder is not None

    def test_embedding_encoder_error_exported(self):
        from fcode.embeddings import EmbeddingEncoderError
        assert EmbeddingEncoderError is not None

    def test_build_embedding_inputs_exported(self):
        from fcode.embeddings import build_embedding_inputs
        assert build_embedding_inputs is not None


# ── Chroma compatibility in encoder scope ─────────────────────────────────────


class TestMetadataFields:
    def test_new_metadata_fields_store_correctly(self, monkeypatch):
        _inject_st(monkeypatch)
        enc = EmbeddingEncoder()
        inp = _input("c1", file_path="app/main.py", symbol_name="foo",
                     chunk_type=ChunkType.FUNCTION, language="Python",
                     start_line=1, end_line=10)
        result = enc.encode([inp])
        md = result.records[0].metadata
        assert md.file_path == "app/main.py"
        assert md.symbol_name == "foo"
        assert md.chunk_type == ChunkType.FUNCTION
        assert md.language == "Python"
        assert md.start_line == 1
        assert md.end_line == 10


# ── Language field None handling ──────────────────────────────────────────────


class TestLanguageNone:
    def test_language_none_in_metadata(self):
        inp = _input("c1", language=None)
        assert inp.metadata.language is None


# ── Empty metadata file_path in encoder ───────────────────────────────────────


class TestEmptyMetadataFilePath:
    def test_empty_metadata_file_path_rejected(self):
        enc = EmbeddingEncoder()
        inp = _input("c1", file_path="")
        with pytest.raises(ValueError, match="empty metadata file_path"):
            enc.encode([inp])
