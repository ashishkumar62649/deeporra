"""Structural tests — verify WP0 protocol interfaces are structurally sound."""

from fcode.contracts.interfaces import (
    ScannerProtocol,
    PythonParserProtocol,
    GraphBuilderProtocol,
    ChunkerProtocol,
    EmbeddingEncoderProtocol,
    SQLiteStoreProtocol,
    ChromaStoreProtocol,
    FTSStoreProtocol,
    GraphStoreProtocol,
    IndexServiceProtocol,
    StatusServiceProtocol,
)


class TestProtocolsStructure:
    def test_scanner_has_scan_method(self):
        assert hasattr(ScannerProtocol, "scan")

    def test_parser_has_parse_method(self):
        assert hasattr(PythonParserProtocol, "parse")

    def test_graph_builder_has_build_method(self):
        assert hasattr(GraphBuilderProtocol, "build")

    def test_chunker_has_chunk_method(self):
        assert hasattr(ChunkerProtocol, "chunk")

    def test_encoder_has_ensure_available(self):
        assert hasattr(EmbeddingEncoderProtocol, "ensure_available")

    def test_encoder_has_encode_method(self):
        assert hasattr(EmbeddingEncoderProtocol, "encode")

    def test_sqlite_store_methods(self):
        assert hasattr(SQLiteStoreProtocol, "store_index_run")
        assert hasattr(SQLiteStoreProtocol, "get_index_status")
        assert hasattr(SQLiteStoreProtocol, "store_file_records")
        assert hasattr(SQLiteStoreProtocol, "store_graph")
        assert hasattr(SQLiteStoreProtocol, "store_chunks")
        assert hasattr(SQLiteStoreProtocol, "reset")

    def test_chroma_store_methods(self):
        assert hasattr(ChromaStoreProtocol, "store_embeddings")
        assert hasattr(ChromaStoreProtocol, "reset")
        assert hasattr(ChromaStoreProtocol, "count")

    def test_fts_store_methods(self):
        assert hasattr(FTSStoreProtocol, "rebuild")
        assert hasattr(FTSStoreProtocol, "reset")

    def test_index_service_methods(self):
        assert hasattr(IndexServiceProtocol, "run_index")
        assert hasattr(IndexServiceProtocol, "get_status")
        assert hasattr(IndexServiceProtocol, "get_counts")

    def test_status_service_methods(self):
        assert hasattr(StatusServiceProtocol, "get_status")
        assert hasattr(StatusServiceProtocol, "doctor")


class TestConcreteSignatureMatch:
    """Concrete implementations must match their Protocol signatures."""

    def test_graph_store_store_graph_signature(self):
        import inspect
        from fcode.storage.graph_store import GraphStore
        proto_sig = inspect.signature(GraphStoreProtocol.store_graph)
        impl_sig = inspect.signature(GraphStore.store_graph)
        assert list(proto_sig.parameters.keys()) == list(impl_sig.parameters.keys())

    def test_graph_store_reset_signature(self):
        import inspect
        from fcode.storage.graph_store import GraphStore
        proto_sig = inspect.signature(GraphStoreProtocol.reset)
        impl_sig = inspect.signature(GraphStore.reset)
        assert list(proto_sig.parameters.keys()) == list(impl_sig.parameters.keys())

    def test_fts_store_rebuild_signature(self):
        import inspect
        from fcode.storage.fts_store import FTSStore
        proto_sig = inspect.signature(FTSStoreProtocol.rebuild)
        impl_sig = inspect.signature(FTSStore.rebuild)
        assert list(proto_sig.parameters.keys()) == list(impl_sig.parameters.keys())

    def test_fts_store_reset_signature(self):
        import inspect
        from fcode.storage.fts_store import FTSStore
        proto_sig = inspect.signature(FTSStoreProtocol.reset)
        impl_sig = inspect.signature(FTSStore.reset)
        assert list(proto_sig.parameters.keys()) == list(impl_sig.parameters.keys())

    def test_chunker_protocol_signature(self):
        import inspect
        sig = inspect.signature(ChunkerProtocol.chunk)
        params = list(sig.parameters.keys())
        assert "scanned_files" in params
        assert "parsed_files" in params
        assert params[0] == "self"
        assert params[1] == "scanned_files"
        assert params[2] == "parsed_files"

    def test_chunker_concrete_param_names(self):
        from fcode.chunking import Chunker
        import inspect
        proto_params = list(inspect.signature(ChunkerProtocol.chunk).parameters.keys())
        impl_params = list(inspect.signature(Chunker.chunk).parameters.keys())
        assert proto_params == impl_params


class TestEmbeddingEncoderAnnotation:
    """Resolved annotation must be Sequence[EmbeddingInput], not list."""

    def test_protocol_has_encode_method(self):
        assert hasattr(EmbeddingEncoderProtocol, "encode")

    def test_encoder_input_annotation_is_sequence(self):
        import inspect
        from typing import get_origin, get_args, get_type_hints
        from collections.abc import Sequence
        from fcode.embeddings.encoder import EmbeddingEncoder
        from fcode.contracts.models import EmbeddingInput, EmbeddingBatchResult

        proto_hints = get_type_hints(EmbeddingEncoderProtocol.encode)
        conc_hints = get_type_hints(EmbeddingEncoder.encode)

        params = list(inspect.signature(EmbeddingEncoderProtocol.encode).parameters.keys())
        assert params[0] == "self"
        assert params[1] == "inputs"

        proto_input = proto_hints["inputs"]
        assert get_origin(proto_input) is Sequence
        assert get_args(proto_input) == (EmbeddingInput,)
        assert proto_input is not list

        conc_input = conc_hints["inputs"]
        assert get_origin(conc_input) is Sequence
        assert get_args(conc_input) == (EmbeddingInput,)

        assert proto_hints["return"] is EmbeddingBatchResult
        assert conc_hints["return"] is EmbeddingBatchResult
