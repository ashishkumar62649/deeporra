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
