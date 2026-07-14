"""Semantic chunk creation — produces CodeChunk values from scanner and parser output.

The chunker is the only pipeline component that creates chunks.
It receives sanitized scanner content and parsed Python structure.
It never reopens original repository files.
"""

import hashlib
import re
import uuid
from typing import Any, Optional, Sequence

from deeporra.contracts.enums import ChunkType, FileType, ParseStatus, SymbolType
from deeporra.contracts.models import CodeChunk, ParsedFile, ScannedFile


CONFIG_EXTENSIONS = frozenset({
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
})
CONFIG_NAMES = frozenset({
    "requirements.txt", "pyproject.toml", "makefile", "dockerfile",
    ".gitignore", ".deeporraignore",
})
CONFIG_PREFIXES = ("requirements-",)


class Chunker:
    """Deterministic chunk creator. Produces CodeChunk values from scanner and parser records."""

    def chunk(
        self,
        scanned_files: Sequence[ScannedFile],
        parsed_files: Sequence[ParsedFile],
    ) -> list[CodeChunk]:
        self._validate_inputs(scanned_files, parsed_files)

        parsed_by_id = {pf.file_id: pf for pf in parsed_files}

        chunks: list[CodeChunk] = []
        for sf in scanned_files:
            pf = parsed_by_id.get(sf.file_id)
            ext = self._get_extension(sf.file_path)

            if ext in (".py", ".pyw"):
                chunks.extend(self._chunk_python(sf, pf))
            elif ext == ".md":
                chunks.extend(self._chunk_markdown(sf))
            elif ext == ".rst":
                chunks.extend(self._chunk_rst(sf))
            elif self._is_config_file(sf):
                chunks.extend(self._chunk_config(sf))
            elif sf.file_type == FileType.DOC:
                pass
            else:
                pass

        return self._sort_chunks(chunks)

    # ── Input validation ─────────────────────────────────────────────────────

    @staticmethod
    def _validate_inputs(
        scanned_files: Sequence[ScannedFile],
        parsed_files: Sequence[ParsedFile],
    ) -> None:
        scanned_ids = [sf.file_id for sf in scanned_files]
        if len(scanned_ids) != len(set(scanned_ids)):
            raise ValueError("duplicate scanned file_id values are invalid")

        parsed_ids = [pf.file_id for pf in parsed_files]
        if len(parsed_ids) != len(set(parsed_ids)):
            raise ValueError("duplicate parsed file_id values are invalid")

        parsed_id_set = set(parsed_ids)
        scanned_id_set = set(scanned_ids)
        for pf in parsed_files:
            if pf.file_id not in scanned_id_set:
                raise ValueError(
                    f"parsed file {pf.file_id} has no matching scanned file"
                )

        for sf in scanned_files:
            ext = sf.file_path.lower().rsplit(".", 1)[-1] if "." in sf.file_path else ""
            if ext in ("py", "pyw"):
                if sf.file_id not in parsed_id_set:
                    raise ValueError(
                        f"Python file {sf.file_path} requires a matching parsed file"
                    )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_extension(path: str) -> str:
        idx = path.rfind(".")
        if idx == -1:
            return ""
        return path[idx:].lower()

    @staticmethod
    def _is_config_file(sf: ScannedFile) -> bool:
        ext = sf.file_path.lower().rsplit(".", 1)[-1] if "." in sf.file_path else ""
        full_ext = "." + ext if ext else ""
        if full_ext in CONFIG_EXTENSIONS:
            return True
        name_lower = sf.file_path.rsplit("/", 1)[-1].lower() if "/" in sf.file_path else sf.file_path.lower()
        if name_lower in CONFIG_NAMES:
            return True
        for prefix in CONFIG_PREFIXES:
            if name_lower.startswith(prefix) and name_lower.endswith(".txt"):
                return True
        return False

    @staticmethod
    def _determine_language(sf: ScannedFile) -> Optional[str]:
        ext = sf.file_path.lower().rsplit(".", 1)[-1] if "." in sf.file_path else ""
        if ext in ("py", "pyw"):
            return "Python"
        if ext == "md":
            return "Markdown"
        if ext == "rst":
            return "RST"
        return None

    @staticmethod
    def _get_lines(content: str) -> list[str]:
        return content.split("\n")

    @staticmethod
    def _safe_get_lines(sf: ScannedFile, start: int, end: int) -> str:
        lines = sf.safe_content.split("\n")
        lines_len = len(lines)
        start_idx = max(0, start - 1)
        end_idx = min(end, lines_len)
        if start_idx >= end_idx:
            return ""
        return "\n".join(lines[start_idx:end_idx])

    # ── Chunk identity ──────────────────────────────────────────────────────

    def _make_chunk_id(
        self,
        file_id: str,
        chunk_type: ChunkType,
        start_line: int,
        end_line: int,
        symbol_id: Optional[str],
        content_hash: str,
    ) -> str:
        raw = f"{file_id}|{chunk_type.value}|{start_line}|{end_line}|{symbol_id or ''}|{content_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))

    @staticmethod
    def _make_content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ── Ordering ─────────────────────────────────────────────────────────────

    @staticmethod
    def _sort_key(chunk: CodeChunk) -> tuple:
        return (
            chunk.file_path.casefold(),
            chunk.file_path,
            chunk.start_line,
            chunk.end_line,
            chunk.chunk_type.value,
            chunk.symbol_name or "",
            chunk.chunk_id,
        )

    def _sort_chunks(self, chunks: list[CodeChunk]) -> list[CodeChunk]:
        return sorted(chunks, key=self._sort_key)

    # ── Python chunking ──────────────────────────────────────────────────────

    def _chunk_python(
        self, sf: ScannedFile, pf: Optional[ParsedFile]
    ) -> list[CodeChunk]:
        if not sf.safe_content.strip():
            return []

        chunks: list[CodeChunk] = []
        has_parse_error = pf is not None and pf.status == ParseStatus.ERROR

        summary = self._make_file_summary(sf, pf, has_parse_error)
        if summary is not None:
            chunks.append(summary)

        if has_parse_error or pf is None:
            return chunks

        route_symbol_ids = {r.route_id for r in pf.routes}

        for sym in pf.symbols:
            if sym.symbol_type == SymbolType.VARIABLE:
                continue

            if sym.symbol_id in route_symbol_ids:
                continue

            if self._is_test_symbol(sym, pf):
                ctype = ChunkType.TEST
            elif sym.symbol_type == SymbolType.FUNCTION:
                ctype = ChunkType.FUNCTION
            elif sym.symbol_type == SymbolType.CLASS:
                ctype = ChunkType.CLASS
            elif sym.symbol_type == SymbolType.METHOD:
                ctype = ChunkType.METHOD
            else:
                continue

            chunk = self._make_symbol_chunk(sf, sym, ctype, pf)
            if chunk is not None:
                chunks.append(chunk)

        for route in pf.routes:
            chunk = self._make_route_chunk(sf, route, pf)
            if chunk is not None:
                chunks.append(chunk)

        return chunks

    @staticmethod
    def _is_test_symbol(sym, pf) -> bool:
        if sym.name.startswith("test_"):
            return True
        if sym.symbol_type == SymbolType.CLASS and sym.name.startswith("Test"):
            return True
        if pf.file_type == FileType.TEST:
            return True
        return False

    def _make_file_summary(
        self, sf: ScannedFile, pf: Optional[ParsedFile], has_parse_error: bool
    ) -> Optional[CodeChunk]:
        lines = sf.safe_content.split("\n")
        max_summary = min(20, len(lines))
        summary_lines = lines[:max_summary]
        parts: list[str] = []
        seen: set[str] = set()

        docstring = pf.docstring if pf and pf.docstring else None
        if docstring and docstring not in seen:
            parts.append(docstring)
            seen.add(docstring)

        if pf and not has_parse_error:
            import_texts: list[str] = []
            for imp in pf.imports:
                if imp.module_name:
                    txt = f"import {imp.module_name}"
                else:
                    txt = f"import {', '.join(imp.imported_names)}"
                if txt not in seen:
                    import_texts.append(txt)
                    seen.add(txt)
            if import_texts:
                parts.extend(import_texts)

        first_lines = "\n".join(summary_lines)
        if first_lines not in seen:
            parts.append(first_lines)

        content = "\n".join(parts) if parts else ""
        if not content:
            return None

        c_hash = self._make_content_hash(content)
        chunk_id = self._make_chunk_id(
            sf.file_id, ChunkType.FILE_SUMMARY, 1,
            min(20, sf.line_count) if sf.line_count else 1,
            None, c_hash,
        )
        return CodeChunk(
            chunk_id=chunk_id,
            file_id=sf.file_id,
            chunk_type=ChunkType.FILE_SUMMARY,
            content=content,
            start_line=1,
            end_line=min(20, sf.line_count) if sf.line_count else 1,
            language="Python",
            file_path=sf.file_path,
            content_hash=c_hash,
            metadata={
                "has_secrets": sf.has_secrets,
                "parse_status": pf.status.value if pf else "not_applicable",
            },
        )

    def _make_symbol_chunk(
        self, sf: ScannedFile, sym, ctype: ChunkType, pf: ParsedFile
    ) -> Optional[CodeChunk]:
        content = self._safe_get_lines(sf, sym.start_line, sym.end_line)
        if not content:
            return None

        if ctype == ChunkType.CLASS:
            content = self._make_class_summary(sf, sym)
            if not content:
                return None

        c_hash = self._make_content_hash(content)
        chunk_id = self._make_chunk_id(
            sf.file_id, ctype, sym.start_line, sym.end_line,
            sym.symbol_id, c_hash,
        )
        meta: dict[str, Any] = {
            "has_secrets": sf.has_secrets,
            "parse_status": pf.status.value,
            "qualified_name": sym.qualified_name or sym.name,
        }
        if sym.signature:
            meta["signature"] = sym.signature
        if sym.docstring:
            meta["docstring"] = sym.docstring
        if sym.parent_symbol_id:
            meta["parent_symbol_id"] = sym.parent_symbol_id

        return CodeChunk(
            chunk_id=chunk_id,
            file_id=sf.file_id,
            chunk_type=ctype,
            content=content,
            start_line=sym.start_line,
            end_line=sym.end_line,
            language="Python",
            file_path=sf.file_path,
            symbol_id=sym.symbol_id,
            symbol_name=sym.name,
            content_hash=c_hash,
            metadata=meta,
        )

    def _make_class_summary(self, sf: ScannedFile, sym) -> str:
        lines = sf.safe_content.split("\n")
        if sym.start_line < 1 or sym.end_line > len(lines):
            return ""
        class_lines = lines[sym.start_line - 1 : sym.end_line]
        if not class_lines:
            return ""
        header = class_lines[0]
        parts: list[str] = [header]
        docstring = sym.docstring
        if docstring:
            parts.append(docstring)

        method_signatures: list[str] = []
        for sib in sym.metadata.get("methods", []) if sym.metadata else []:
            method_signatures.append(sib)

        return "\n".join(parts)

    def _make_route_chunk(
        self, sf: ScannedFile, route, pf: ParsedFile
    ) -> Optional[CodeChunk]:
        line_count = sf.line_count or len(sf.safe_content.split("\n"))
        handler_end = line_count
        if route.start_line < 1:
            return None

        for sym in pf.symbols:
            if sym.symbol_id == route.route_id:
                handler_end = sym.end_line
                break

        content = self._safe_get_lines(sf, route.start_line, handler_end)
        if not content:
            return None

        c_hash = self._make_content_hash(content)
        chunk_id = self._make_chunk_id(
            sf.file_id, ChunkType.ROUTE, route.start_line, handler_end,
            route.route_id, c_hash,
        )
        meta: dict[str, Any] = {
            "has_secrets": sf.has_secrets,
            "parse_status": pf.status.value,
            "http_method": route.method.value,
            "route_path": route.route_path,
            "handler_function": route.handler_function,
            "decorators": list(route.decorators) if route.decorators else [],
            "qualified_name": route.handler_function,
        }

        return CodeChunk(
            chunk_id=chunk_id,
            file_id=sf.file_id,
            chunk_type=ChunkType.ROUTE,
            content=content,
            start_line=route.start_line,
            end_line=handler_end,
            language="Python",
            file_path=sf.file_path,
            symbol_id=route.route_id,
            symbol_name=f"{route.method.value} {route.route_path}",
            content_hash=c_hash,
            metadata=meta,
        )

    # ── Documentation chunking ───────────────────────────────────────────────

    def _chunk_markdown(self, sf: ScannedFile) -> list[CodeChunk]:
        if not sf.safe_content.strip():
            return []
        return self._split_doc_chunks(sf, r"^(#{1,6})\s")

    def _chunk_rst(self, sf: ScannedFile) -> list[CodeChunk]:
        if not sf.safe_content.strip():
            return []
        return self._split_doc_chunks(sf, self._RST_HEADING_PATTERN)

    _RST_HEADING_PATTERN = re.compile(
        r"^([=\-~^`:'\"\._*+#<>!@$%&]){3,}\s*$", re.MULTILINE
    )

    @classmethod
    def _find_rst_headings(cls, content: str) -> list[tuple[int, str, str]]:
        lines = content.split("\n")
        headings: list[tuple[int, str, str]] = []
        for i, line in enumerate(lines):
            if i + 1 < len(lines) and cls._RST_HEADING_PATTERN.match(lines[i + 1]):
                marker = lines[i + 1][0]
                headings.append((i + 1, line.strip(), marker))
        return headings

    def _split_doc_chunks(self, sf: ScannedFile, md_pattern: str) -> list[CodeChunk]:
        content = sf.safe_content
        lines = content.split("\n")
        is_rst = sf.file_path.lower().endswith(".rst")

        if is_rst:
            heading_spans: list[tuple[int, int, str, str]] = []
            for i, line in enumerate(lines):
                if i + 1 < len(lines) and re.match(r"^([=\-~^`:'\"\._*+#<>!@$%&]){3,}\s*$", lines[i + 1]):
                    marker = lines[i + 1][0]
                    heading_spans.append((i + 1, i + 2, line.strip(), marker))
            return self._build_doc_chunks(sf, content, heading_spans)

        heading_spans: list[tuple[int, int, str, str]] = []
        for i, line in enumerate(lines):
            m = re.match(md_pattern, line)
            if m:
                level = len(m.group(1))
                heading_text = line.lstrip("#").strip()
                heading_spans.append((i + 1, i + 1, heading_text, str(level)))

        return self._build_doc_chunks(sf, content, heading_spans)

    def _build_doc_chunks(
        self,
        sf: ScannedFile,
        content: str,
        heading_spans: list[tuple[int, int, str, str]],
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        lines = content.split("\n")
        total_lines = len(lines)
        prev_end = 0

        for idx, (hdr_line, _, heading_text, heading_level) in enumerate(heading_spans):
            if prev_end < hdr_line - 1:
                preamble = "\n".join(lines[prev_end : hdr_line - 1])
                preamble = preamble.strip()
                if preamble:
                    c_hash = self._make_content_hash(preamble)
                    chunk_id = self._make_chunk_id(
                        sf.file_id, ChunkType.README_SECTION,
                        prev_end + 1, hdr_line - 1, None, c_hash,
                    )
                    chunks.append(CodeChunk(
                        chunk_id=chunk_id,
                        file_id=sf.file_id,
                        chunk_type=ChunkType.README_SECTION,
                        content=preamble,
                        start_line=prev_end + 1,
                        end_line=hdr_line - 1,
                        language=self._determine_language(sf),
                        file_path=sf.file_path,
                        content_hash=c_hash,
                        metadata={
                            "has_secrets": sf.has_secrets,
                            "parse_status": "not_applicable",
                        },
                    ))

            section_start = hdr_line - 1
            if idx + 1 < len(heading_spans):
                next_section_start = heading_spans[idx + 1][0] - 1
                section_lines = lines[section_start:next_section_start]
            else:
                section_lines = lines[section_start:]

            section_content = "\n".join(section_lines).strip()
            if not section_content:
                prev_end = section_start + len(section_lines)
                continue

            section_end_line = section_start + len(section_lines)

            c_hash = self._make_content_hash(section_content)
            chunk_id = self._make_chunk_id(
                sf.file_id, ChunkType.README_SECTION,
                hdr_line, section_end_line, None, c_hash,
            )
            meta: dict[str, Any] = {
                "has_secrets": sf.has_secrets,
                "parse_status": "not_applicable",
                "heading": heading_text,
                "heading_level": heading_level,
            }
            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                file_id=sf.file_id,
                chunk_type=ChunkType.README_SECTION,
                content=section_content,
                start_line=hdr_line,
                end_line=section_end_line,
                language=self._determine_language(sf),
                file_path=sf.file_path,
                content_hash=c_hash,
                metadata=meta,
            ))

            prev_end = section_start + len(section_lines)

        if heading_spans and prev_end < total_lines:
            rest = "\n".join(lines[prev_end:]).strip()
            if rest:
                c_hash = self._make_content_hash(rest)
                chunk_id = self._make_chunk_id(
                    sf.file_id, ChunkType.README_SECTION,
                    prev_end + 1, total_lines, None, c_hash,
                )
                chunks.append(CodeChunk(
                    chunk_id=chunk_id,
                    file_id=sf.file_id,
                    chunk_type=ChunkType.README_SECTION,
                    content=rest,
                    start_line=prev_end + 1,
                    end_line=total_lines,
                    language=self._determine_language(sf),
                    file_path=sf.file_path,
                    content_hash=c_hash,
                    metadata={
                        "has_secrets": sf.has_secrets,
                        "parse_status": "not_applicable",
                    },
                ))

        if not heading_spans and content.strip():
            c_hash = self._make_content_hash(content.strip())
            chunk_id = self._make_chunk_id(
                sf.file_id, ChunkType.README_SECTION,
                1, total_lines, None, c_hash,
            )
            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                file_id=sf.file_id,
                chunk_type=ChunkType.README_SECTION,
                content=content.strip(),
                start_line=1,
                end_line=total_lines,
                language=self._determine_language(sf),
                file_path=sf.file_path,
                content_hash=c_hash,
                metadata={
                    "has_secrets": sf.has_secrets,
                    "parse_status": "not_applicable",
                },
            ))

        return chunks

    # ── Configuration chunking ──────────────────────────────────────────────

    def _chunk_config(self, sf: ScannedFile) -> list[CodeChunk]:
        if not sf.safe_content.strip():
            return []

        lines = sf.safe_content.split("\n")
        total = len(lines)
        chunks: list[CodeChunk] = []
        block_size = 100

        for i in range(0, total, block_size):
            block_lines = lines[i : i + block_size]
            block_content = "\n".join(block_lines)
            if not block_content.strip():
                continue

            start_line = i + 1
            end_line = min(i + block_size, total)
            block_idx = i // block_size
            block_count = (total + block_size - 1) // block_size

            c_hash = self._make_content_hash(block_content)
            chunk_id = self._make_chunk_id(
                sf.file_id, ChunkType.CONFIG,
                start_line, end_line, None, c_hash,
            )
            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                file_id=sf.file_id,
                chunk_type=ChunkType.CONFIG,
                content=block_content,
                start_line=start_line,
                end_line=end_line,
                language=self._determine_language(sf),
                file_path=sf.file_path,
                content_hash=c_hash,
                metadata={
                    "has_secrets": sf.has_secrets,
                    "parse_status": "not_applicable",
                    "block_index": block_idx,
                    "block_count": block_count,
                },
            ))

        return chunks
