"""Index service — orchestrates the scan → parse → chunk → embed → graph pipeline.

Step 2 (committed): repository validation, scanner, parser, chunker — in memory only.
Step 3 (committed): embedding-input construction, encoder call, graph-builder call.
Results remain entirely in memory. No storage, FTS, Chroma, or persistence.
Step 4 (current): SQLite metadata + FTS staging on the same `sqlite3.Connection`.
Successful result remains nonterminal (state=STORING, completed_phase=GRAPH,
persistent_replacement_started=True). No full replacement, no vectors, no
graph-store writes. Replacement and promotion are deferred to Step 5.
"""

import hashlib
import math
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Sequence

from fcode.contracts import (
    ChunkerProtocol,
    CodeChunk,
    DiagnosticSeverity,
    EmbeddingBatchResult,
    EmbeddingEncoderProtocol,
    EmbeddingInput,
    EmbeddingRecord,
    ErrorCode,
    FCodeConfig,
    FTSStoreProtocol,
    GraphBuildResult,
    GraphBuilderProtocol,
    GraphEdgeInput,
    GraphNodeInput,
    IndexBuildResult,
    IndexCounts,
    IndexDiagnostic,
    IndexPhase,
    IndexRunResult,
    IndexState,
    ParseStatus,
    ParsedFile,
    PythonParserProtocol,
    RepoInput,
    ScanResult,
    ScannedFile,
    ScannerProtocol,
    SQLiteStoreProtocol,
)
from fcode.embeddings import build_embedding_inputs, EXPECTED_DIMENSION
from fcode.indexing.full_rebuild import FullRebuildCoordinator
from fcode.indexing.sqlite_fts_persistence import (
    AlreadyIndexedRepositoryError,
    run_step4_persistence,
)
from fcode.indexing.state_machine import IndexStateMachine


@dataclass
class _AttemptScaffolding:
    """Per-attempt scaffolding returned by IndexService._fresh_attempt().

    Holds either:
    - the live IndexStateMachine + diagnostic lists for a started attempt
      (`fatal is None`), or
    - a fatal IndexBuildResult short-circuiting the attempt
      (`fatal is not None`).
    """
    sm: Optional[IndexStateMachine]
    diagnostics: list[IndexDiagnostic]
    compat_errors: list[str]
    fatal: Optional[IndexBuildResult] = None


class IndexService:
    """Dependency-injected indexing orchestrator.

    Step 2: scan → parse → chunk (build_through_chunking)
    Step 3: +embed → graph (build_through_graphing)
    Step 4: +SQLite metadata + FTS staging (build_through_sqlite_fts)
    """

    def __init__(
        self,
        scanner: ScannerProtocol,
        parser: PythonParserProtocol,
        chunker: ChunkerProtocol,
        *,
        encoder: Optional[EmbeddingEncoderProtocol] = None,
        graph_builder: Optional[GraphBuilderProtocol] = None,
        sqlite_store: Optional[SQLiteStoreProtocol] = None,
        fts_store: Optional[FTSStoreProtocol] = None,
    ) -> None:
        if scanner is None:
            raise TypeError("scanner must not be None")
        if parser is None:
            raise TypeError("parser must not be None")
        if chunker is None:
            raise TypeError("chunker must not be None")
        self._scanner = scanner
        self._parser = parser
        self._chunker = chunker
        self._encoder = encoder
        self._graph_builder = graph_builder
        self._sqlite_store = sqlite_store
        self._fts_store = fts_store

    # ── Public operations ──────────────────────────────────────────────────

    def build_through_chunking(
        self,
        config: FCodeConfig,
    ) -> IndexBuildResult:
        scaffolding = self._fresh_attempt(config)
        if scaffolding.fatal is not None:
            return scaffolding.fatal
        sm, diagnostics, compat_errors = scaffolding.sm, scaffolding.diagnostics, scaffolding.compat_errors
        result = self._run_step2(sm, diagnostics, compat_errors)
        if result is not None:
            return result
        return self._build_chunking_result(sm, diagnostics, compat_errors)

    def build_through_graphing(
        self,
        config: FCodeConfig,
    ) -> IndexBuildResult:
        if not isinstance(config, FCodeConfig):
            raise TypeError(
                f"expected FCodeConfig, got {type(config).__name__}"
            )
        if self._encoder is None:
            raise TypeError("encoder is required for build_through_graphing")
        if self._graph_builder is None:
            raise TypeError("graph_builder is required for build_through_graphing")
        scaffolding = self._fresh_attempt(config)
        if scaffolding.fatal is not None:
            return scaffolding.fatal
        sm, diagnostics, compat_errors = scaffolding.sm, scaffolding.diagnostics, scaffolding.compat_errors
        result = self._run_step2(sm, diagnostics, compat_errors)
        if result is not None:
            return result
        return self._run_step3(sm, diagnostics, compat_errors)

    def build_through_sqlite_fts(
        self,
        config: FCodeConfig,
    ) -> IndexBuildResult:
        if not isinstance(config, FCodeConfig):
            raise TypeError(
                f"expected FCodeConfig, got {type(config).__name__}"
            )
        if self._encoder is None:
            raise TypeError("encoder is required for build_through_sqlite_fts")
        if self._graph_builder is None:
            raise TypeError("graph_builder is required for build_through_sqlite_fts")
        if self._sqlite_store is None:
            raise TypeError("sqlite_store is required for build_through_sqlite_fts")
        if self._fts_store is None:
            raise TypeError("fts_store is required for build_through_sqlite_fts")
        scaffolding = self._fresh_attempt(config)
        if scaffolding.fatal is not None:
            return scaffolding.fatal
        sm, diagnostics, compat_errors = scaffolding.sm, scaffolding.diagnostics, scaffolding.compat_errors
        result = self._run_step2(sm, diagnostics, compat_errors)
        if result is not None:
            return result
        step3_result = self._run_step3(sm, diagnostics, compat_errors)
        if step3_result.run_result.state == IndexState.ERROR:
            return step3_result
        return self._run_step4(sm, diagnostics, compat_errors)

    def build_complete_index(self, config: FCodeConfig) -> IndexBuildResult:
        """Build and safely promote one complete local index generation."""
        if not isinstance(config, FCodeConfig):
            raise TypeError(f"expected FCodeConfig, got {type(config).__name__}")
        if self._encoder is None:
            raise TypeError("encoder is required for build_complete_index")
        if self._graph_builder is None:
            raise TypeError("graph_builder is required for build_complete_index")
        scaffolding = self._fresh_attempt(config)
        if scaffolding.fatal is not None:
            return scaffolding.fatal
        sm, diagnostics, compat_errors = (
            scaffolding.sm,
            scaffolding.diagnostics,
            scaffolding.compat_errors,
        )
        result = self._run_step2(sm, diagnostics, compat_errors)
        if result is not None:
            return result
        step3_result = self._run_step3(sm, diagnostics, compat_errors)
        if step3_result.run_result.state == IndexState.ERROR:
            return step3_result
        return self._run_complete(sm, diagnostics, compat_errors)

    def run_index(self, config: FCodeConfig) -> IndexRunResult:
        """Run one complete indexing attempt and return its final run result."""
        return self.build_complete_index(config).run_result

    # ── Per-attempt scaffolding ─────────────────────────────────────────────

    def _fresh_attempt(self, config: FCodeConfig) -> _AttemptScaffolding:
        """Validate `_validate_config` up-front and create one attempt scaffolding.

        Returns an `_AttemptScaffolding` with `sm`, diagnostics, and compat_errors
        always populated. On validation failure the scaffolding's `fatal` field
        carries the fatal IndexBuildResult and the caller must short-circuit.
        """
        if not isinstance(config, FCodeConfig):
            raise TypeError(
                f"expected FCodeConfig, got {type(config).__name__}"
            )
        sm = IndexStateMachine()
        diagnostics: list[IndexDiagnostic] = []
        compat_errors: list[str] = []

        validation_error = self._validate_config(config)
        if validation_error is not None:
            diag, compat = validation_error
            diagnostics.append(diag)
            compat_errors.append(compat)
            fatal = self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR, None
            )
            return _AttemptScaffolding(
                sm=None, diagnostics=diagnostics,
                compat_errors=compat_errors, fatal=fatal,
            )

        resolved_path = str(Path(config.repo_path).resolve())
        self._resolved_repo_path = resolved_path
        self._repo_input = RepoInput(
            repo_path=resolved_path,
            max_files=config.max_files,
            max_size_bytes=config.max_size_bytes,
            skip_hidden=not config.scan_hidden,
            skip_binary=True,
        )
        self._att_config = config

        return _AttemptScaffolding(
            sm=sm, diagnostics=diagnostics, compat_errors=compat_errors,
        )

    # ── Step 2 — validation, scanning, parsing, chunking ──────────────────

    def _run_step2(
        self,
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
    ):
        """Run validation is done by `_fresh_attempt`. Then SCAN → PARSE → CHUNK.

        Returns None on success (caller proceeds). Returns a fatal
        IndexBuildResult on any failure. State machine is mutated on the
        consumed-side.
        """
        repo_input = self._repo_input

        # ── SCANNING ────────────────────────────────────────────────────────
        sm.transition(IndexState.SCANNING)

        scan_result: ScanResult
        try:
            scan_result = self._scanner.scan(repo_input, self._att_config)
        except BaseException:
            diag = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="File scanning failed unexpectedly.",
                phase=IndexPhase.SCAN,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR, scan_result=None
            )

        scan_validation = self._validate_scan_result(scan_result, self._att_config)
        if scan_validation is not None:
            diag, compat = scan_validation
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result,
            )

        warning_diags = self._convert_scanner_warnings(scan_result)
        diagnostics.extend(warning_diags)

        # ── PARSING ─────────────────────────────────────────────────────────
        sm.transition(IndexState.PARSING)

        candidates = [
            sf for sf in scan_result.files
            if sf.parse_status == ParseStatus.PENDING and not sf.is_binary
        ]

        parsed_files: list[ParsedFile] = []
        parse_ok_count = 0
        parse_err_count = 0
        symbol_count = 0

        for sf in candidates:
            try:
                pf = self._parser.parse(sf)
            except BaseException:
                diag = IndexDiagnostic(
                    code=ErrorCode.PARSE_FAILED.value,
                    message="Python parsing failed unexpectedly.",
                    phase=IndexPhase.PARSE,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                diagnostics.append(diag)
                compat_errors.append(diag.message)
                return self._build_fatal(
                    sm, diagnostics, compat_errors, IndexState.ERROR,
                    scan_result=scan_result, parsed_files=parsed_files,
                )

            parse_valid = self._validate_parse_result(pf, sf)
            if parse_valid is not None:
                diag, compat = parse_valid
                diagnostics.append(diag)
                compat_errors.append(compat)
                return self._build_fatal(
                    sm, diagnostics, compat_errors, IndexState.ERROR,
                    scan_result=scan_result, parsed_files=parsed_files,
                )

            parsed_files.append(pf)

            if pf.status == ParseStatus.PARSED:
                parse_ok_count += 1
            elif pf.status == ParseStatus.ERROR:
                parse_err_count += 1
                wdiag = IndexDiagnostic(
                    code="parse_warning",
                    message="Python file could not be parsed.",
                    phase=IndexPhase.PARSE,
                    recoverable=True,
                    severity=DiagnosticSeverity.WARNING,
                    repo_relative_path=pf.file_path,
                )
                diagnostics.append(wdiag)

            symbol_count += len(pf.symbols)

        # ── CHUNKING ────────────────────────────────────────────────────────
        sm.transition(IndexState.CHUNKING)

        chunks: list[CodeChunk] = []
        try:
            chunks = self._chunker.chunk(scan_result.files, parsed_files)
        except BaseException:
            diag = IndexDiagnostic(
                code="chunk_failed",
                message="Semantic chunk creation failed.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
            )

        chunk_valid = self._validate_chunks(chunks, scan_result.files)
        if chunk_valid is not None:
            diag, compat = chunk_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
            )

        # Step 2 intermediate results retained for downstream methods.
        self._step2_data = dict(
            scan_result=scan_result,
            parsed_files=parsed_files,
            chunks=chunks,
            parse_ok_count=parse_ok_count,
            parse_err_count=parse_err_count,
            symbol_count=symbol_count,
        )
        return None

    def _build_chunking_result(
        self,
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
    ) -> IndexBuildResult:
        d2 = self._step2_data
        scanned_count = d2["scan_result"].eligible_file_count
        counts = IndexCounts(
            scanned=scanned_count,
            parsed=d2["parse_ok_count"],
            chunks=len(d2["chunks"]),
            parse_errors=d2["parse_err_count"],
            symbols=d2["symbol_count"],
            warnings=len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]),
            errors=len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]),
        )
        run_result = IndexRunResult(
            state=sm.state,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )
        counts.validate()
        run_result.validate()
        for d in diagnostics:
            d.validate()
        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=d2["scan_result"],
            parsed_files=d2["parsed_files"],
            chunks=d2["chunks"],
            embedding_result=None,
            graph_result=None,
        )

    # ── Step 3: embedding and graph orchestration ──────────────────────────

    def _run_step3(
        self,
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
    ) -> IndexBuildResult:
        d2 = self._step2_data
        scan_result: ScanResult = d2["scan_result"]
        parsed_files: list[ParsedFile] = d2["parsed_files"]
        chunks: list[CodeChunk] = d2["chunks"]
        parse_ok_count: int = d2["parse_ok_count"]
        parse_err_count: int = d2["parse_err_count"]
        symbol_count: int = d2["symbol_count"]

        chunk_valid = self._validate_chunks(chunks, scan_result.files)
        if chunk_valid is not None:
            diag, compat = chunk_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
            )

        # ── Scan count ─────────────────────────────────────────────────────
        scanned_count = scan_result.eligible_file_count

        # ── EMBEDDING ───────────────────────────────────────────────────────
        sm.transition(IndexState.EMBEDDING)

        embedding_inputs: list[EmbeddingInput] = []
        try:
            embedding_inputs = build_embedding_inputs(chunks)
        except BaseException:
            diag = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding input construction failed.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks,
            )

        if not isinstance(embedding_inputs, list):
            diag = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding input construction returned an invalid type.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks,
            )

        embedding_result: EmbeddingBatchResult
        try:
            embedding_result = self._encoder.encode(embedding_inputs)
        except BaseException as exc:
            embedding_result = self._extract_partial_result(exc)
            if embedding_result is not None:
                embed_validation = self._validate_embedding_result(
                    embedding_result, embedding_inputs
                )
                if embed_validation is not None:
                    diag, compat = embed_validation
                    diagnostics.append(diag)
                    compat_errors.append(compat)
                    return self._build_fatal(
                        sm, diagnostics, compat_errors, IndexState.ERROR,
                        scan_result=scan_result, parsed_files=parsed_files,
                        chunks=chunks, embedding_result=embedding_result,
                    )
                # All eligible failed
                if (embedding_result.eligible_count > 0
                        and embedding_result.success_count == 0
                        and embedding_result.fail_count == embedding_result.eligible_count):
                    diag = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED.value,
                        message="All eligible chunks failed to embed.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    diagnostics.append(diag)
                    compat_errors.append(diag.message)
                    return self._build_fatal(
                        sm, diagnostics, compat_errors, IndexState.ERROR,
                        scan_result=scan_result, parsed_files=parsed_files,
                        chunks=chunks, embedding_result=embedding_result,
                    )
                # Partial success from exception — continue
            else:
                diag = self._embedding_exception_to_diagnostic(exc)
                diagnostics.append(diag)
                compat_errors.append(diag.message)
                return self._build_fatal(
                    sm, diagnostics, compat_errors, IndexState.ERROR,
                    scan_result=scan_result, parsed_files=parsed_files,
                    chunks=chunks,
                )

        embed_valid = self._validate_embedding_result(embedding_result, embedding_inputs)
        if embed_valid is not None:
            diag, compat = embed_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        # Embedding outcome checks
        if (embedding_result.eligible_count > 0
                and embedding_result.success_count == 0
                and embedding_result.fail_count == embedding_result.eligible_count):
            diag = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED.value,
                message="All eligible chunks failed to embed.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        # Embedding warnings
        embed_warnings = self._convert_embedding_warnings(embedding_result)
        diagnostics.extend(embed_warnings)

        # ── Counts up to embedding ──────────────────────────────────────────
        counts = IndexCounts(
            scanned=scanned_count,
            parsed=parse_ok_count,
            chunks=len(chunks),
            parse_errors=parse_err_count,
            symbols=symbol_count,
            embedding_eligible=embedding_result.eligible_count,
            embedded=embedding_result.success_count,
            embedding_skipped=embedding_result.skipped_count,
            embedding_failed=embedding_result.fail_count,
            warnings=len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]),
            errors=len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]),
        )

        # ── GRAPHING ────────────────────────────────────────────────────────
        sm.transition(IndexState.GRAPHING)

        graph_result: GraphBuildResult
        try:
            graph_result = self._graph_builder.build(parsed_files)
        except BaseException:
            diag = IndexDiagnostic(
                code="graph_failed",
                message="Code graph construction failed.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            counts.graph_nodes = 0
            counts.graph_edges = 0
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        graph_valid = self._validate_graph_result(graph_result, scan_result)
        if graph_valid is not None:
            diag, compat = graph_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        counts.graph_nodes = graph_result.node_count
        counts.graph_edges = graph_result.edge_count

        # Save complete-step-3 outputs for downstream _run_step4 use.
        self._step3_embedding_result = embedding_result
        self._step3_graph_result = graph_result

        run_result = IndexRunResult(
            state=sm.state,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )
        counts.validate()
        run_result.validate()
        for d in diagnostics:
            d.validate()

        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=scan_result,
            parsed_files=parsed_files,
            chunks=chunks,
            embedding_result=embedding_result,
            graph_result=graph_result,
        )

    # ── Step 4 — SQLite metadata + FTS staging ────────────────────────────

    def _run_step4(
        self,
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
    ) -> IndexBuildResult:
        """STORING phase: stage metadata files/symbols/chunks and rebuild FTS.

        Successful STORING state is nonterminal. Vector/graph persistence are
        deferred to Step 5. On fatal failure: ERROR with completed phase GRAPH
        and `persistent_replacement_started=True`.
        """
        d2 = self._step2_data
        scan_result: ScanResult = d2["scan_result"]
        parsed_files: list[ParsedFile] = d2["parsed_files"]
        chunks: list[CodeChunk] = d2["chunks"]
        parse_ok_count: int = d2["parse_ok_count"]
        parse_err_count: int = d2["parse_err_count"]
        symbol_count: int = d2["symbol_count"]
        embedding_result: EmbeddingBatchResult = getattr(self, "_step3_embedding_result", None)
        graph_result: GraphBuildResult = getattr(self, "_step3_graph_result", None)

        if embedding_result is None or graph_result is None:
            diag = IndexDiagnostic(
                code=ErrorCode.PERSIST_FAILED.value,
                message="Index metadata persistence failed.",
                phase=IndexPhase.PERSIST,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        # ── STORING transition (state machine flips persistence-started) ─────
        try:
            sm.transition(IndexState.STORING)
        except Exception as exc:
            diag = IndexDiagnostic(
                code=ErrorCode.PERSIST_FAILED.value,
                message="Index metadata persistence failed.",
                phase=IndexPhase.PERSIST,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            return self._build_fatal(
                sm, diagnostics, compat_errors, IndexState.ERROR,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
                graph_result=graph_result,
            )

        sqlite_store = self._sqlite_store
        fts_store = self._fts_store

        # Stage metadata + FTS in one transactional attempt on the shared
        # `sqlite_store.conn`.
        warning_count = len(
            [d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]
        )
        try:
            run_step4_persistence(
                scan_result=scan_result,
                parsed_files=parsed_files,
                chunks=chunks,
                sqlite_store=sqlite_store,
                fts_store=fts_store,
                repo_path=self._resolved_repo_path,
                warning_count=warning_count,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
        except AlreadyIndexedRepositoryError:
            diag = IndexDiagnostic(
                code=ErrorCode.PERSIST_FAILED.value,
                message="Index metadata persistence failed.",
                phase=IndexPhase.PERSIST,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
                details="an active repository row already exists for this path",
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            counts = IndexCounts(
                scanned=scan_result.eligible_file_count,
                parsed=parse_ok_count,
                chunks=len(chunks),
                parse_errors=parse_err_count,
                symbols=symbol_count,
                embedding_eligible=embedding_result.eligible_count,
                embedded=embedding_result.success_count,
                embedding_skipped=embedding_result.skipped_count,
                embedding_failed=embedding_result.fail_count,
                graph_nodes=graph_result.node_count,
                graph_edges=graph_result.edge_count,
                warnings=len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]),
                errors=len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]),
            )
            failed = self._build_step4_fatal(
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
                graph_result=graph_result, counts=counts,
            )
            return failed
        except Exception:
            diag = IndexDiagnostic(
                code=ErrorCode.PERSIST_FAILED.value,
                message="Index metadata persistence failed.",
                phase=IndexPhase.PERSIST,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            diagnostics.append(diag)
            compat_errors.append(diag.message)
            counts = IndexCounts(
                scanned=scan_result.eligible_file_count,
                parsed=parse_ok_count,
                chunks=len(chunks),
                parse_errors=parse_err_count,
                symbols=symbol_count,
                embedding_eligible=embedding_result.eligible_count,
                embedded=embedding_result.success_count,
                embedding_skipped=embedding_result.skipped_count,
                embedding_failed=embedding_result.fail_count,
                graph_nodes=graph_result.node_count,
                graph_edges=graph_result.edge_count,
                warnings=len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]),
                errors=len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR]),
            )
            return self._build_step4_fatal(
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
                graph_result=graph_result, counts=counts,
            )

        counts = IndexCounts(
            scanned=scan_result.eligible_file_count,
            parsed=parse_ok_count,
            chunks=len(chunks),
            parse_errors=parse_err_count,
            symbols=symbol_count,
            embedding_eligible=embedding_result.eligible_count,
            embedded=embedding_result.success_count,
            embedding_skipped=embedding_result.skipped_count,
            embedding_failed=embedding_result.fail_count,
            graph_nodes=graph_result.node_count,
            graph_edges=graph_result.edge_count,
            warnings=warning_count,
            errors=0,
        )

        run_result = IndexRunResult(
            state=sm.state,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )
        counts.validate()
        run_result.validate()
        for d in diagnostics:
            d.validate()

        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=scan_result,
            parsed_files=parsed_files,
            chunks=chunks,
            embedding_result=embedding_result,
            graph_result=graph_result,
        )

    def _run_complete(
        self,
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
    ) -> IndexBuildResult:
        d2 = self._step2_data
        scan_result: ScanResult = d2["scan_result"]
        parsed_files: list[ParsedFile] = d2["parsed_files"]
        chunks: list[CodeChunk] = d2["chunks"]
        embedding_result: EmbeddingBatchResult = self._step3_embedding_result
        graph_result: GraphBuildResult = self._step3_graph_result
        counts = IndexCounts(
            scanned=scan_result.eligible_file_count,
            parsed=d2["parse_ok_count"],
            chunks=len(chunks),
            parse_errors=d2["parse_err_count"],
            symbols=d2["symbol_count"],
            embedding_eligible=embedding_result.eligible_count,
            embedded=embedding_result.success_count,
            embedding_skipped=embedding_result.skipped_count,
            embedding_failed=embedding_result.fail_count,
            graph_nodes=graph_result.node_count,
            graph_edges=graph_result.edge_count,
            warnings=len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING]),
        )
        try:
            sm.transition(IndexState.STORING)
            outcome = FullRebuildCoordinator(self._resolved_repo_path).build(
                scan_result=scan_result,
                parsed_files=parsed_files,
                chunks=chunks,
                embedding_result=embedding_result,
                graph_result=graph_result,
                counts=counts,
            )
            if outcome.cleanup_warning:
                diagnostics.append(IndexDiagnostic(
                    code="cleanup_warning",
                    message="Previous inactive index cleanup was deferred.",
                    phase=IndexPhase.PERSIST,
                    recoverable=True,
                    severity=DiagnosticSeverity.WARNING,
                ))
                counts.warnings += 1
            sm.transition(IndexState.COMPLETE)
        except Exception:
            diagnostics.append(IndexDiagnostic(
                code=ErrorCode.PERSIST_FAILED.value,
                message="Index persistence failed.",
                phase=IndexPhase.PERSIST,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            ))
            compat_errors.append("Index persistence failed.")
            return self._build_step4_fatal(
                sm,
                diagnostics,
                compat_errors,
                scan_result=scan_result,
                parsed_files=parsed_files,
                chunks=chunks,
                embedding_result=embedding_result,
                graph_result=graph_result,
                counts=counts,
            )

        run_result = IndexRunResult(
            state=sm.state,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )
        counts.validate()
        run_result.validate()
        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=scan_result,
            parsed_files=parsed_files,
            chunks=chunks,
            embedding_result=embedding_result,
            graph_result=graph_result,
        )

    @staticmethod
    def _build_step4_fatal(
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
        *,
        scan_result: ScanResult,
        parsed_files: list[ParsedFile],
        chunks: list[CodeChunk],
        embedding_result: EmbeddingBatchResult,
        graph_result: GraphBuildResult,
        counts: IndexCounts,
    ) -> IndexBuildResult:
        """Build a fatal IndexBuildResult after a STORING-phase failure, leaving
        `persistent_replacement_started=True` and current state moved to ERROR.
        """
        if sm.state != IndexState.ERROR:
            sm.fail()

        fatal_count = len([d for d in diagnostics
                          if d.severity == DiagnosticSeverity.ERROR and not d.recoverable])
        warn_count = len([d for d in diagnostics
                         if d.severity == DiagnosticSeverity.WARNING])
        counts.errors = fatal_count
        counts.warnings = warn_count

        run_result = IndexRunResult(
            state=sm.state,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )

        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=scan_result,
            parsed_files=parsed_files,
            chunks=chunks,
            embedding_result=embedding_result,
            graph_result=graph_result,
        )

    # ── Embedding helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_partial_result(exc: BaseException) -> Optional[EmbeddingBatchResult]:
        # Check for EmbeddingEncoderError with result
        if hasattr(exc, "result") and isinstance(exc.result, EmbeddingBatchResult):
            return exc.result
        return None

    @staticmethod
    def _embedding_exception_to_diagnostic(exc: BaseException) -> IndexDiagnostic:
        code = ErrorCode.EMBEDDING_FAILED.value
        message = "Embedding generation failed unexpectedly."
        if hasattr(exc, "code") and isinstance(exc.code, ErrorCode):
            code = exc.code.value
            if exc.code == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE:
                message = "Local embedding model is unavailable."
            elif exc.code == ErrorCode.EMBEDDING_DIMENSION_MISMATCH:
                message = "Embedding vectors do not match the required dimension."
            elif exc.code == ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED:
                message = "All eligible chunks failed to embed."
        return IndexDiagnostic(
            code=code,
            message=message,
            phase=IndexPhase.EMBED,
            recoverable=False,
            severity=DiagnosticSeverity.ERROR,
        )

    @staticmethod
    def _convert_embedding_warnings(
        result: EmbeddingBatchResult,
    ) -> list[IndexDiagnostic]:
        result_warnings: list[IndexDiagnostic] = []
        seen_ids: set[str] = set()
        for w in getattr(result, "warnings", []):
            if not isinstance(w, dict):
                result_warnings.append(IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_CHUNK_WARNING.value,
                    message="One or more eligible chunks could not be embedded.",
                    phase=IndexPhase.EMBED,
                    recoverable=True,
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue
            chunk_id = w.get("chunk_id", "")
            raw_code = w.get("code", "")
            safe_code = raw_code if isinstance(raw_code, str) and raw_code else ErrorCode.EMBEDDING_CHUNK_WARNING.value
            warn_msg = "One or more eligible chunks could not be embedded."
            safe_path: Optional[str] = None
            raw_path = w.get("repo_relative_path") or w.get("path") or w.get("file_path")
            if isinstance(raw_path, str) and raw_path:
                if (not raw_path.startswith("/")
                        and not raw_path.startswith("\\")
                        and ".." not in raw_path.split("/")):
                    safe_path = raw_path.replace("\\", "/")
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
            result_warnings.append(IndexDiagnostic(
                code=safe_code,
                message=warn_msg,
                phase=IndexPhase.EMBED,
                recoverable=True,
                severity=DiagnosticSeverity.WARNING,
                repo_relative_path=safe_path,
            ))
        if result.fail_count > 0 and not result_warnings:
            result_warnings.append(IndexDiagnostic(
                code=ErrorCode.EMBEDDING_CHUNK_WARNING.value,
                message="One or more eligible chunks could not be embedded.",
                phase=IndexPhase.EMBED,
                recoverable=True,
                severity=DiagnosticSeverity.WARNING,
            ))
        return result_warnings

    @staticmethod
    def _validate_embedding_result(
        result: EmbeddingBatchResult,
        inputs: list[EmbeddingInput],
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        if not isinstance(result, EmbeddingBatchResult):
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedder returned an invalid result type.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        for field_name in ("eligible_count", "success_count", "fail_count", "skipped_count"):
            val = getattr(result, field_name, -1)
            if isinstance(val, bool) or not isinstance(val, int):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message=f"Embedding result {field_name} is not an integer.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if val < 0:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message=f"Embedding result {field_name} is negative.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

        if result.success_count != len(result.records):
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding success_count does not match records length.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.success_count + result.fail_count != result.eligible_count:
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding count invariant: success + fail != eligible.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.eligible_count + result.skipped_count != len(inputs):
            d = IndexDiagnostic(
                code=ErrorCode.EMBEDDING_FAILED.value,
                message="Embedding count invariant: eligible + skipped != total inputs.",
                phase=IndexPhase.EMBED,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        input_ids = [inp.chunk_id for inp in inputs]
        seen_ids: set[str] = set()

        for rec in result.records:
            if not isinstance(rec, EmbeddingRecord):
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding result contains a non-EmbeddingRecord item.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not rec.chunk_id:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record has an empty chunk_id.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if rec.chunk_id in seen_ids:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding records contain a duplicate chunk_id.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_ids.add(rec.chunk_id)

            if rec.chunk_id not in input_ids:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record references an unknown chunk_id.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if rec.metadata.chunk_id != rec.chunk_id:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_FAILED.value,
                    message="Embedding record metadata chunk_id mismatch.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            # Order: check record order follows eligible input order
            eligible_inputs = [inp for inp in inputs if inp.chunk_id in seen_ids]
            for i, rec_ci in enumerate(r.chunk_id for r in result.records):
                if i < len(eligible_inputs) and rec_ci != eligible_inputs[i].chunk_id:
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding record order does not match input order.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message

            # Vector validation
            vec = rec.vector
            if len(vec) != EXPECTED_DIMENSION:
                d = IndexDiagnostic(
                    code=ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value,
                    message=f"Embedding vector length {len(vec)} != {EXPECTED_DIMENSION}.",
                    phase=IndexPhase.EMBED,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            for v in vec:
                if isinstance(v, bool):
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding vector contains a boolean value.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if not isinstance(v, (int, float)):
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding vector contains a non-numeric value.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if math.isnan(v) or math.isinf(v):
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding vector contains NaN or infinity.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message

            # Metadata path safety
            md_path = rec.metadata.file_path
            if md_path:
                if md_path.startswith("/") or md_path.startswith("\\"):
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding record has an absolute file_path in metadata.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if ".." in md_path.split("/"):
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding record has a traversal file_path in metadata.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if "\\" in md_path:
                    d = IndexDiagnostic(
                        code=ErrorCode.EMBEDDING_FAILED.value,
                        message="Embedding record has a backslash file_path in metadata.",
                        phase=IndexPhase.EMBED,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message

        return None

    # ── Graph helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _validate_graph_result(
        result: GraphBuildResult,
        scan_result: ScanResult,
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        if not isinstance(result, GraphBuildResult):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph builder returned an invalid result type.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        scanned_paths = {sf.file_path for sf in scan_result.files}
        nodes = result.nodes
        edges = result.edges

        if not isinstance(nodes, list):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph nodes is not a list.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not isinstance(edges, list):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph edges is not a list.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        seen_node_ids: set[str] = set()
        seen_node_record_ids: set[str] = set()

        for node in nodes:
            if not isinstance(node, GraphNodeInput):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node list contains a non-GraphNodeInput item.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not node.node_id:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node has an empty node_id.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if node.node_id in seen_node_ids:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph contains duplicate node IDs.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_node_ids.add(node.node_id)

            if not node.record_id:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node has an empty record_id.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if node.record_id in seen_node_record_ids:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph contains duplicate node record IDs.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_node_record_ids.add(node.record_id)

            if not node.node_type:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph node has an empty node_type.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            # Path safety
            sf = node.source_file
            if sf:
                if sf.startswith("/") or sf.startswith("\\"):
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph node has an absolute source_file.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if ".." in sf.split("/"):
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph node source_file contains traversal.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if "\\" in sf:
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph node source_file contains backslash.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message

        seen_edge_ids: set[str] = set()
        seen_canonical_edges: set[tuple[str, str, str, str, str]] = set()

        for edge in edges:
            if not isinstance(edge, GraphEdgeInput):
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge list contains a non-GraphEdgeInput item.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not edge.record_id:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge has an empty record_id.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if edge.record_id in seen_edge_ids:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph contains duplicate edge record IDs.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_edge_ids.add(edge.record_id)

            canonical_edge = (
                edge.source_node_id or "",
                edge.target_node_id or "",
                edge.relation.value if edge.relation else "",
                edge.source_file or "",
                edge.source_location or "",
            )
            if canonical_edge in seen_canonical_edges:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph contains duplicate canonical edge tuples.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_canonical_edges.add(canonical_edge)

            if not edge.source_node_id:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge has an empty source_node_id.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not edge.target_node_id:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge has an empty target_node_id.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not edge.relation:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge has an empty relation.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            # Endpoint integrity — source and target must be known nodes
            if edge.source_node_id not in seen_node_ids:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge source_node_id does not reference a known node.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if edge.target_node_id not in seen_node_ids:
                d = IndexDiagnostic(
                    code="graph_failed",
                    message="Graph edge target_node_id does not reference a known node.",
                    phase=IndexPhase.GRAPH,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            # Edge path safety
            esf = edge.source_file
            if esf:
                if esf.startswith("/") or esf.startswith("\\"):
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph edge source_file is absolute.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if ".." in esf.split("/"):
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph edge source_file contains traversal.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message
                if "\\" in esf:
                    d = IndexDiagnostic(
                        code="graph_failed",
                        message="Graph edge source_file contains backslash.",
                        phase=IndexPhase.GRAPH,
                        recoverable=False,
                        severity=DiagnosticSeverity.ERROR,
                    )
                    return d, d.message

        if result.node_count != len(nodes):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph result node_count does not match nodes list length.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.edge_count != len(edges):
            d = IndexDiagnostic(
                code="graph_failed",
                message="Graph result edge_count does not match edges list length.",
                phase=IndexPhase.GRAPH,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        return None

    # ── Private helpers (Step 2) ───────────────────────────────────────────

    @staticmethod
    def _build_fatal(
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
        final_state: IndexState,
        scan_result: Optional[ScanResult],
        parsed_files: Optional[list[ParsedFile]] = None,
        chunks: Optional[list[CodeChunk]] = None,
        embedding_result: Optional[EmbeddingBatchResult] = None,
    ) -> IndexBuildResult:
        if sm.state != IndexState.ERROR:
            sm.fail()

        fatal_count = len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR and not d.recoverable])
        warn_count = len([d for d in diagnostics if d.severity == DiagnosticSeverity.WARNING])

        counts = IndexCounts(
            warnings=warn_count,
            errors=fatal_count,
        )

        run_result = IndexRunResult(
            state=IndexState.ERROR,
            phase=sm.phase,
            counts=counts,
            diagnostics=diagnostics,
            errors=compat_errors,
        )

        return IndexBuildResult(
            run_result=run_result,
            completed_phase=sm.completed_phase,
            state_history=sm.history,
            persistent_replacement_started=sm.persistent_replacement_started,
            scan_result=scan_result,
            parsed_files=parsed_files or [],
            chunks=chunks or [],
            embedding_result=embedding_result,
            graph_result=None,
        )

    @staticmethod
    def _validate_config(
        config: FCodeConfig,
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        path = config.repo_path
        if not path or not isinstance(path, str):
            d = IndexDiagnostic(
                code=ErrorCode.INVALID_REPOSITORY_PATH.value,
                message="Repository path is missing or is not a readable directory.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        p = Path(path)
        if not p.exists():
            d = IndexDiagnostic(
                code=ErrorCode.INVALID_REPOSITORY_PATH.value,
                message="Repository path is missing or is not a readable directory.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not p.is_dir():
            d = IndexDiagnostic(
                code=ErrorCode.INVALID_REPOSITORY_PATH.value,
                message="Repository path is missing or is not a readable directory.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if not os.access(str(p), os.R_OK | os.X_OK):
            d = IndexDiagnostic(
                code="permission_denied",
                message="Repository path is not readable.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        max_files = config.max_files
        if isinstance(max_files, bool) or not isinstance(max_files, int):
            d = IndexDiagnostic(
                code="config_invalid",
                message="max_files must be a positive integer.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if max_files <= 0:
            d = IndexDiagnostic(
                code="config_invalid",
                message="max_files must be a positive integer.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        max_bytes = config.max_size_bytes
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            d = IndexDiagnostic(
                code="config_invalid",
                message="max_size_bytes must be a positive integer.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if max_bytes <= 0:
            d = IndexDiagnostic(
                code="config_invalid",
                message="max_size_bytes must be a positive integer.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        return None

    @staticmethod
    def _validate_scan_result(
        result: ScanResult,
        config: FCodeConfig,
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        if not isinstance(result, ScanResult):
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner returned an invalid result type.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        files = result.files
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()

        for sf in files:
            if not sf.file_id:
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned a file without an ID.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if sf.file_id in seen_ids:
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned duplicate file IDs.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_ids.add(sf.file_id)

            if not sf.file_path:
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned a file without a path.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if sf.file_path.startswith("/") or sf.file_path.startswith("\\"):
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned an absolute file path.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ".." in sf.file_path.split("/"):
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned a path with '..' traversal.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if "\\" in sf.file_path:
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned a path with backslash separators.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if sf.file_path in seen_paths:
                d = IndexDiagnostic(
                    code=ErrorCode.SCAN_FAILED.value,
                    message="Scanner returned duplicate file paths.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_paths.add(sf.file_path)

        ec = result.eligible_file_count
        if ec != len(files):
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner eligible_file_count does not match files length.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        tc = result.total_count
        if tc != len(files):
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner total_count does not match files length.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.eligible_file_count < 0:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner eligible_file_count is negative.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.eligible_total_bytes < 0:
            d = IndexDiagnostic(
                code=ErrorCode.SCAN_FAILED.value,
                message="Scanner eligible_total_bytes is negative.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.eligible_file_count > config.max_files:
            d = IndexDiagnostic(
                code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
                message="Repository exceeds maximum file count.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        if result.eligible_total_bytes > config.max_size_bytes:
            d = IndexDiagnostic(
                code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
                message="Repository exceeds maximum content size.",
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        for sk in result.skipped:
            if sk.reason == "repository_limit_exceeded":
                d = IndexDiagnostic(
                    code=ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value,
                    message="Repository exceeds indexing limits.",
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

        return None

    @staticmethod
    def _convert_scanner_warnings(
        scan_result: ScanResult,
    ) -> list[IndexDiagnostic]:
        result: list[IndexDiagnostic] = []
        for w in scan_result.warnings:
            if not isinstance(w, dict):
                result.append(IndexDiagnostic(
                    code=ErrorCode.FILE_SKIPPED.value,
                    message="A file was skipped during scanning.",
                    phase=IndexPhase.SCAN,
                    recoverable=True,
                    severity=DiagnosticSeverity.WARNING,
                ))
                continue
            code = w.get("code") or ErrorCode.FILE_SKIPPED.value
            if not isinstance(code, str):
                code = ErrorCode.FILE_SKIPPED.value
            msg = w.get("message") or "A file was skipped during scanning."
            if not isinstance(msg, str):
                msg = "A file was skipped during scanning."
            msg = msg[:500]
            raw_path = w.get("repo_relative_path") or w.get("path") or w.get("file_path")
            safe_path: Optional[str] = None
            if isinstance(raw_path, str) and raw_path:
                if (not raw_path.startswith("/")
                        and not raw_path.startswith("\\")
                        and ".." not in raw_path.split("/")):
                    safe_path = raw_path.replace("\\", "/")
            result.append(IndexDiagnostic(
                code=code,
                message=msg,
                phase=IndexPhase.SCAN,
                recoverable=True,
                severity=DiagnosticSeverity.WARNING,
                repo_relative_path=safe_path,
            ))
        return result

    @staticmethod
    def _validate_parse_result(
        pf: ParsedFile,
        sf: ScannedFile,
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        if not isinstance(pf, ParsedFile):
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned an invalid result type.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if pf.file_id != sf.file_id:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned mismatched file ID.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if pf.file_path != sf.file_path:
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned mismatched file path.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message
        if pf.status not in (ParseStatus.PARSED, ParseStatus.ERROR, ParseStatus.NOT_APPLICABLE):
            d = IndexDiagnostic(
                code=ErrorCode.PARSE_FAILED.value,
                message="Parser returned a file with PENDING status.",
                phase=IndexPhase.PARSE,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        seen_sym: set[str] = set()
        for sym in pf.symbols:
            if not sym.symbol_id:
                d = IndexDiagnostic(
                    code=ErrorCode.PARSE_FAILED.value,
                    message="Parser returned a symbol without an ID.",
                    phase=IndexPhase.PARSE,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if sym.symbol_id in seen_sym:
                d = IndexDiagnostic(
                    code=ErrorCode.PARSE_FAILED.value,
                    message="Parser returned duplicate symbol IDs.",
                    phase=IndexPhase.PARSE,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_sym.add(sym.symbol_id)

        seen_route: set[str] = set()
        for rt in pf.routes:
            if not rt.route_id:
                d = IndexDiagnostic(
                    code=ErrorCode.PARSE_FAILED.value,
                    message="Parser returned a route without an ID.",
                    phase=IndexPhase.PARSE,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if rt.route_id in seen_route:
                d = IndexDiagnostic(
                    code=ErrorCode.PARSE_FAILED.value,
                    message="Parser returned duplicate route IDs.",
                    phase=IndexPhase.PARSE,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_route.add(rt.route_id)

        return None

    @staticmethod
    def _validate_chunks(
        chunks: list[CodeChunk],
        scanned_files: Sequence[ScannedFile],
    ) -> Optional[tuple[IndexDiagnostic, str]]:
        if not isinstance(chunks, list):
            d = IndexDiagnostic(
                code="chunk_failed",
                message="Chunker returned an invalid result type.",
                phase=IndexPhase.CHUNK,
                recoverable=False,
                severity=DiagnosticSeverity.ERROR,
            )
            return d, d.message

        scanned_ids = {sf.file_id for sf in scanned_files}
        scanned_paths = {sf.file_path for sf in scanned_files}
        seen_ids: set[str] = set()

        for ch in chunks:
            if not isinstance(ch, CodeChunk):
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a non-CodeChunk item.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not ch.chunk_id:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a chunk without an ID.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ch.chunk_id in seen_ids:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned duplicate chunk IDs.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            seen_ids.add(ch.chunk_id)

            if ch.file_id not in scanned_ids:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker referenced unknown file ID.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if ch.file_path not in scanned_paths:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker referenced unknown file path.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            fp = ch.file_path
            if fp.startswith("/") or fp.startswith("\\"):
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned an absolute file path.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ".." in fp.split("/"):
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a path with '..' traversal.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if "\\" in fp:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a path with backslash separators.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if ch.start_line < 1:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a chunk with invalid start_line.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message
            if ch.end_line < ch.start_line:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a chunk with end_line < start_line.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            if not isinstance(ch.content, str) or not ch.content.strip():
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a chunk with empty content.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

            expected_hash = hashlib.sha256(ch.content.encode("utf-8")).hexdigest()
            if ch.content_hash and ch.content_hash != expected_hash:
                d = IndexDiagnostic(
                    code="chunk_failed",
                    message="Chunker returned a chunk with incorrect content hash.",
                    phase=IndexPhase.CHUNK,
                    recoverable=False,
                    severity=DiagnosticSeverity.ERROR,
                )
                return d, d.message

        return None
