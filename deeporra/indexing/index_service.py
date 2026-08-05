"""Index service — orchestrates the scan → parse → chunk → embed → graph pipeline.

Step 2 (committed): repository validation, scanner, parser, chunker — in memory only.
Step 3 (committed): embedding-input construction, encoder call, graph-builder call.
Results remain entirely in memory. No storage, FTS, Chroma, or persistence.
Step 4 (current): SQLite metadata + FTS staging on the same `sqlite3.Connection`.
Successful result remains nonterminal (state=STORING, completed_phase=GRAPH,
persistent_replacement_started=True). No full replacement, no vectors, no
graph-store writes. Replacement and promotion are deferred to Step 5.

Validation and warning-conversion helpers live in `deeporra.indexing.validation`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from deeporra.contracts import (
    ChunkerProtocol,
    CodeChunk,
    DiagnosticSeverity,
    EmbeddingBatchResult,
    EmbeddingEncoderProtocol,
    EmbeddingInput,
    ErrorCode,
    DeepOrraConfig,
    FTSStoreProtocol,
    GraphBuildResult,
    GraphBuilderProtocol,
    IndexBuildResult,
    IndexCounts,
    IndexDiagnostic,
    IndexPhase,
    IndexRunResult,
    IndexStatusRecord,
    IndexState,
    ParseStatus,
    ParsedFile,
    PythonParserProtocol,
    RepoInput,
    ScanResult,
    ScannerProtocol,
    SQLiteStoreProtocol,
)
from deeporra.embeddings import build_embedding_inputs
from deeporra.indexing.full_rebuild import FullRebuildCoordinator
from deeporra.indexing.sqlite_fts_persistence import (
    AlreadyIndexedRepositoryError,
    run_step4_persistence,
)
from deeporra.indexing.validation import (
    convert_embedding_warnings,
    convert_scanner_warnings,
    embedding_exception_to_diagnostic,
    extract_partial_result,
    validate_chunks,
    validate_config,
    validate_embedding_result,
    validate_graph_result,
    validate_parse_result,
    validate_scan_result,
)
from deeporra.indexing.state_machine import IndexStateMachine


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
        status_reader=None,
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
        self._status_reader = status_reader

    # ── Public operations ──────────────────────────────────────────────────

    def build_through_chunking(
        self,
        config: DeepOrraConfig,
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
        config: DeepOrraConfig,
    ) -> IndexBuildResult:
        if not isinstance(config, DeepOrraConfig):
            raise TypeError(
                f"expected DeepOrraConfig, got {type(config).__name__}"
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
        config: DeepOrraConfig,
    ) -> IndexBuildResult:
        if not isinstance(config, DeepOrraConfig):
            raise TypeError(
                f"expected DeepOrraConfig, got {type(config).__name__}"
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

    def build_complete_index(self, config: DeepOrraConfig) -> IndexBuildResult:
        """Build and safely promote one complete local index generation."""
        if not isinstance(config, DeepOrraConfig):
            raise TypeError(f"expected DeepOrraConfig, got {type(config).__name__}")
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

    def run_index(self, config: DeepOrraConfig) -> IndexRunResult:
        """Run one complete indexing attempt and return its final run result."""
        return self.build_complete_index(config).run_result

    def get_status(self) -> IndexStatusRecord:
        if self._status_reader is None:
            raise TypeError("status_reader is required for get_status")
        return self._status_reader.read()

    def get_counts(self) -> IndexCounts:
        return self.get_status().counts

    # ── Per-attempt scaffolding ─────────────────────────────────────────────

    def _fresh_attempt(self, config: DeepOrraConfig) -> _AttemptScaffolding:
        """Validate `validate_config` up-front and create one attempt scaffolding.

        Returns an `_AttemptScaffolding` with `sm`, diagnostics, and compat_errors
        always populated. On validation failure the scaffolding's `fatal` field
        carries the fatal IndexBuildResult and the caller must short-circuit.
        """
        if not isinstance(config, DeepOrraConfig):
            raise TypeError(
                f"expected DeepOrraConfig, got {type(config).__name__}"
            )
        sm = IndexStateMachine()
        diagnostics: list[IndexDiagnostic] = []
        compat_errors: list[str] = []

        validation_error = validate_config(config)
        if validation_error is not None:
            diag, compat = validation_error
            diagnostics.append(diag)
            compat_errors.append(compat)
            fatal = self._build_fatal(
                sm, diagnostics, compat_errors, None
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
        except Exception:
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
                sm, diagnostics, compat_errors, scan_result=None
            )

        scan_validation = validate_scan_result(scan_result, self._att_config)
        if scan_validation is not None:
            diag, compat = scan_validation
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors,
                scan_result=scan_result,
            )

        warning_diags = convert_scanner_warnings(scan_result)
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
            except Exception:
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
                    sm, diagnostics, compat_errors,
                    scan_result=scan_result, parsed_files=parsed_files,
                )

            parse_valid = validate_parse_result(pf, sf)
            if parse_valid is not None:
                diag, compat = parse_valid
                diagnostics.append(diag)
                compat_errors.append(compat)
                return self._build_fatal(
                    sm, diagnostics, compat_errors,
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
        except Exception:
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
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
            )

        chunk_valid = validate_chunks(chunks, scan_result.files)
        if chunk_valid is not None:
            diag, compat = chunk_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors,
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

        chunk_valid = validate_chunks(chunks, scan_result.files)
        if chunk_valid is not None:
            diag, compat = chunk_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
            )

        # ── Scan count ─────────────────────────────────────────────────────
        scanned_count = scan_result.eligible_file_count

        # ── EMBEDDING ───────────────────────────────────────────────────────
        sm.transition(IndexState.EMBEDDING)

        embedding_inputs: list[EmbeddingInput] = []
        try:
            embedding_inputs = build_embedding_inputs(chunks)
        except Exception:
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
                sm, diagnostics, compat_errors,
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
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks,
            )

        embedding_result: EmbeddingBatchResult
        try:
            embedding_result = self._encoder.encode(embedding_inputs)
        except Exception as exc:
            embedding_result = extract_partial_result(exc)
            if embedding_result is not None:
                embed_validation = validate_embedding_result(
                    embedding_result, embedding_inputs
                )
                if embed_validation is not None:
                    diag, compat = embed_validation
                    diagnostics.append(diag)
                    compat_errors.append(compat)
                    return self._build_fatal(
                        sm, diagnostics, compat_errors,
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
                        sm, diagnostics, compat_errors,
                        scan_result=scan_result, parsed_files=parsed_files,
                        chunks=chunks, embedding_result=embedding_result,
                    )
                # Partial success from exception — continue
            else:
                diag = embedding_exception_to_diagnostic(exc)
                diagnostics.append(diag)
                compat_errors.append(diag.message)
                return self._build_fatal(
                    sm, diagnostics, compat_errors,
                    scan_result=scan_result, parsed_files=parsed_files,
                    chunks=chunks,
                )

        embed_valid = validate_embedding_result(embedding_result, embedding_inputs)
        if embed_valid is not None:
            diag, compat = embed_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors,
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
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        # Embedding warnings
        embed_warnings = convert_embedding_warnings(embedding_result)
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
        except Exception:
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
                sm, diagnostics, compat_errors,
                scan_result=scan_result, parsed_files=parsed_files,
                chunks=chunks, embedding_result=embedding_result,
            )

        graph_valid = validate_graph_result(graph_result)
        if graph_valid is not None:
            diag, compat = graph_valid
            diagnostics.append(diag)
            compat_errors.append(compat)
            return self._build_fatal(
                sm, diagnostics, compat_errors,
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
                sm, diagnostics, compat_errors,
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
                sm, diagnostics, compat_errors,
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

    # ── Private helpers (Step 2) ───────────────────────────────────────────

    @staticmethod
    def _build_fatal(
        sm: IndexStateMachine,
        diagnostics: list[IndexDiagnostic],
        compat_errors: list[str],
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
