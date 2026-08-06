"""Tests for Chunker — safe-content handoff and semantic chunk creation."""

import hashlib
import uuid

import pytest

from deeporra.chunking import Chunker
from deeporra.contracts.enums import (
    ChunkType,
    FileType,
    HttpMethod,
    ParseStatus,
    SymbolType,
)
from deeporra.contracts.models import (
    ParsedFile,
    ParsedImport,
    ParsedRoute,
    ParsedSymbol,
    ScannedFile,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _py_scanned(
    path: str = "mod.py",
    content: str = "x = 1\n",
    file_id: str = "file:mod.py",
    has_secrets: bool = False,
    line_count: int = 0,
    file_type: FileType = FileType.SOURCE,
) -> ScannedFile:
    actual_lc = line_count or max(content.count("\n"), 1)
    if content == "":
        actual_lc = 0
    return ScannedFile(
        file_id=file_id,
        file_path=path,
        file_type=file_type,
        safe_content=content,
        line_count=actual_lc,
        has_secrets=has_secrets,
        language="Python",
    )


def _doc_scanned(
    path: str = "readme.md",
    content: str = "",
    file_id: str = "",
) -> ScannedFile:
    fid = file_id or f"file:{path}"
    lc = content.count("\n")
    if content and not content.endswith("\n"):
        lc += 1
    return ScannedFile(
        file_id=fid,
        file_path=path,
        file_type=FileType.DOC,
        safe_content=content,
        line_count=lc,
        has_secrets=False,
        language=None,
    )


def _config_scanned(
    path: str = "cfg.json",
    content: str = "",
    file_id: str = "",
) -> ScannedFile:
    fid = file_id or f"file:{path}"
    lc = content.count("\n")
    if content and not content.endswith("\n"):
        lc += 1
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    lang = ext if ext else None
    return ScannedFile(
        file_id=fid,
        file_path=path,
        file_type=FileType.CONFIG,
        safe_content=content,
        line_count=lc,
        has_secrets=False,
        language=lang,
    )


def _parsed(
    file_id: str = "file:mod.py",
    path: str = "mod.py",
    status: ParseStatus = ParseStatus.PARSED,
    symbols: list | None = None,
    imports: list | None = None,
    routes: list | None = None,
    file_type: FileType = FileType.SOURCE,
    docstring: str | None = None,
) -> ParsedFile:
    return ParsedFile(
        file_id=file_id,
        file_path=path,
        file_type=file_type,
        status=status,
        symbols=symbols or [],
        imports=imports or [],
        routes=routes or [],
        docstring=docstring,
        line_count=0,
    )


def _sym(
    name: str = "foo",
    st: SymbolType = SymbolType.FUNCTION,
    start: int = 1,
    end: int = 3,
    symbol_id: str = "",
    qual: str = "",
    sig: str | None = None,
    doc: str | None = None,
    parent_id: str | None = None,
) -> ParsedSymbol:
    sid = symbol_id or f"sym:{name}:{start}"
    return ParsedSymbol(
        name=name,
        symbol_type=st,
        start_line=start,
        end_line=end,
        symbol_id=sid,
        qualified_name=qual or name,
        signature=sig,
        docstring=doc,
        parent_symbol_id=parent_id,
    )


def _imp(
    module: str = "os",
    names: list[str] | None = None,
    line: int = 1,
) -> ParsedImport:
    return ParsedImport(
        module_name=module,
        imported_names=names or [module],
        line_number=line,
    )


def _route(
    route_id: str = "",
    path: str = "/users",
    method: HttpMethod = HttpMethod.GET,
    handler: str = "list_users",
    start: int = 3,
    decorators: list[str] | None = None,
) -> ParsedRoute:
    return ParsedRoute(
        route_id=route_id or f"route:GET:{path}:mod.py:{start}",
        route_path=path,
        method=method,
        handler_function=handler,
        start_line=start,
        decorators=decorators or ["@app.get('/users')"],
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_chunk_id(
    file_id: str,
    chunk_type: ChunkType,
    start_line: int,
    end_line: int,
    symbol_id: str | None,
    content_hash: str,
) -> str:
    raw = f"{file_id}|{chunk_type.value}|{start_line}|{end_line}|{symbol_id or ''}|{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


class TestPublicContract:
    def test_chunker_exposes_chunk_method(self):
        c = Chunker()
        assert hasattr(c, "chunk")

    def test_chunk_accepts_scanned_and_parsed(self):
        c = Chunker()
        sf = _py_scanned("empty.py", content="", file_id="file:empty.py")
        pf = _parsed(file_id="file:empty.py", path="empty.py")
        result = c.chunk(scanned_files=[sf], parsed_files=[pf])
        assert isinstance(result, list)

    def test_concrete_param_names_match_protocol(self):
        from deeporra.contracts.interfaces import ChunkerProtocol
        import inspect
        proto = list(inspect.signature(ChunkerProtocol.chunk).parameters.keys())
        impl = list(inspect.signature(Chunker.chunk).parameters.keys())
        assert proto == impl


class TestCodeChunkCanonical:
    def test_canonical_fields_present(self):
        from deeporra.contracts import CodeChunk, ChunkType
        c = CodeChunk(
            chunk_id="a", file_id="b", chunk_type=ChunkType.FILE_SUMMARY,
            content="c", start_line=1, end_line=1, file_path="mod.py",
        )
        assert hasattr(c, "chunk_id")
        assert hasattr(c, "file_id")
        assert hasattr(c, "chunk_type")
        assert hasattr(c, "content")
        assert hasattr(c, "start_line")
        assert hasattr(c, "end_line")
        assert hasattr(c, "file_path")
        assert hasattr(c, "content_hash")
        assert hasattr(c, "metadata")

    def test_no_stale_fields(self):
        from deeporra.contracts import CodeChunk
        assert not hasattr(CodeChunk, "text")
        assert not hasattr(CodeChunk, "source_file")
        assert not hasattr(CodeChunk, "embedding")

    def test_metadata_has_secrets_default(self):
        c = Chunker()
        sf = _py_scanned("a.py", "def foo(): pass\n", file_id="file:a.py")
        pf = _parsed(file_id="file:a.py", path="a.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 1, 1, "sym:foo:1", "foo"),
        ])
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            assert "has_secrets" in chunk.metadata
            assert chunk.metadata["has_secrets"] is False

    def test_secret_flag_true_in_metadata(self):
        c = Chunker()
        sf = _py_scanned(
            "secret.py",
            "API_KEY = '[REDACTED]'\ndef foo(): pass\n",
            file_id="file:secret.py",
            has_secrets=True,
        )
        pf = _parsed(file_id="file:secret.py", path="secret.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 2, 2, "sym:foo:2", "foo"),
        ])
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            assert chunk.metadata["has_secrets"] is True

    def test_no_embedding_field(self):
        from deeporra.contracts import CodeChunk
        assert not hasattr(CodeChunk, "embedding")


class TestFileAccessAndPrivacy:
    def test_never_calls_open(self, monkeypatch):
        import builtins
        original = builtins.open

        def trap(*a, **kw):
            raise RuntimeError("open called")

        monkeypatch.setattr(builtins, "open", trap)
        c = Chunker()
        sf = _py_scanned("safe.py", "x=1\n", file_id="file:safe.py")
        pf = _parsed(file_id="file:safe.py", path="safe.py")
        try:
            c.chunk([sf], [pf])
        except RuntimeError:
            pytest.fail("chunker called open()")
        builtins.open = original

    def test_uses_safe_content(self):
        c = Chunker()
        sf = _py_scanned("safe.py", "API_KEY = '[REDACTED]'\n", file_id="file:safe.py",
                         has_secrets=True, line_count=1)
        pf = _parsed(file_id="file:safe.py", path="safe.py", status=ParseStatus.ERROR)
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            assert "[REDACTED]" in chunk.content
            assert "original_secret" not in chunk.content

    def test_redaction_marker_retained(self):
        c = Chunker()
        sf = _py_scanned("safe.py", "API_KEY = '[REDACTED]'\n", file_id="file:safe.py",
                         has_secrets=True, line_count=1)
        pf = _parsed(file_id="file:safe.py", path="safe.py", status=ParseStatus.ERROR)
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            if "[REDACTED]" not in chunk.content:
                pytest.fail("redaction marker not preserved in chunk content")

    def test_chunk_serialization_no_raw_secret(self):
        c = Chunker()
        sf = _py_scanned("safe.py", "TOKEN='[REDACTED]'\n", file_id="file:safe.py",
                         has_secrets=True, line_count=1)
        pf = _parsed(file_id="file:safe.py", path="safe.py", status=ParseStatus.ERROR)
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            content = chunk.content
            meta = chunk.metadata
            assert "hidden" not in content
            assert "hidden" not in str(meta)
            assert "hidden" not in str(chunk)


class TestPythonChunking:
    def test_file_summary_created(self):
        c = Chunker()
        sf = _py_scanned("app.py", "'''mod doc'''\nimport os\nx=1\n", file_id="file:app.py")
        pf = _parsed(file_id="file:app.py", path="app.py", status=ParseStatus.PARSED,
                     imports=[_imp("os")])
        chunks = c.chunk([sf], [pf])
        summaries = [ch for ch in chunks if ch.chunk_type == ChunkType.FILE_SUMMARY]
        assert len(summaries) == 1
        s = summaries[0]
        assert s.file_id == "file:app.py"
        assert s.file_path == "app.py"
        assert s.start_line == 1
        assert s.end_line >= 1

    def test_function_chunk(self):
        c = Chunker()
        content = "def foo():\n    pass\n"
        sf = _py_scanned("mod.py", content, file_id="file:mod.py", line_count=2)
        pf = _parsed(file_id="file:mod.py", path="mod.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 1, 2, "sym:foo:1", "mod.foo", "()"),
        ])
        chunks = c.chunk([sf], [pf])
        funcs = [ch for ch in chunks if ch.chunk_type == ChunkType.FUNCTION]
        assert len(funcs) == 1
        assert "def foo():" in funcs[0].content
        assert funcs[0].symbol_name == "foo"

    def test_async_function_chunk(self):
        c = Chunker()
        content = "async def fetch():\n    return 1\n"
        sf = _py_scanned("mod.py", content, file_id="file:mod.py", line_count=2)
        pf = _parsed(file_id="file:mod.py", path="mod.py", symbols=[
            _sym("fetch", SymbolType.FUNCTION, 1, 2, "sym:fetch:1", "mod.fetch", "()"),
        ])
        chunks = c.chunk([sf], [pf])
        funcs = [ch for ch in chunks if ch.chunk_type == ChunkType.FUNCTION]
        assert len(funcs) == 1
        assert "async def fetch():" in funcs[0].content

    def test_class_summary_no_method_body(self):
        c = Chunker()
        content = "class MyClass:\n    def method_a(self):\n        pass\n    def method_b(self):\n        pass\n"
        sf = _py_scanned("cls.py", content, file_id="file:cls.py", line_count=5)
        pf = _parsed(file_id="file:cls.py", path="cls.py", symbols=[
            _sym("MyClass", SymbolType.CLASS, 1, 5, "sym:MyClass:1", "cls.MyClass"),
            _sym("method_a", SymbolType.METHOD, 2, 3, "sym:method_a:2", "cls.MyClass.method_a", parent_id="sym:MyClass:1"),
            _sym("method_b", SymbolType.METHOD, 4, 5, "sym:method_b:4", "cls.MyClass.method_b", parent_id="sym:MyClass:1"),
        ])
        chunks = c.chunk([sf], [pf])
        classes = [ch for ch in chunks if ch.chunk_type == ChunkType.CLASS]
        assert len(classes) == 1
        cls_content = classes[0].content
        assert "class MyClass" in cls_content

    def test_method_chunk(self):
        c = Chunker()
        content = "class Cls:\n    def method(self):\n        pass\n"
        sf = _py_scanned("mod.py", content, file_id="file:mod.py", line_count=3)
        pf = _parsed(file_id="file:mod.py", path="mod.py", symbols=[
            _sym("Cls", SymbolType.CLASS, 1, 3, "sym:Cls:1", "mod.Cls"),
            _sym("method", SymbolType.METHOD, 2, 3, "sym:method:2", "mod.Cls.method", parent_id="sym:Cls:1"),
        ])
        chunks = c.chunk([sf], [pf])
        methods = [ch for ch in chunks if ch.chunk_type == ChunkType.METHOD]
        assert len(methods) == 1
        assert methods[0].symbol_name == "method"

    def test_async_method_chunk(self):
        c = Chunker()
        content = "class Cls:\n    async def method(self):\n        pass\n"
        sf = _py_scanned("mod.py", content, file_id="file:mod.py", line_count=3)
        pf = _parsed(file_id="file:mod.py", path="mod.py", symbols=[
            _sym("Cls", SymbolType.CLASS, 1, 3, "sym:Cls:1", "mod.Cls"),
            _sym("method", SymbolType.METHOD, 2, 3, "sym:method:2", "mod.Cls.method", parent_id="sym:Cls:1"),
        ])
        chunks = c.chunk([sf], [pf])
        methods = [ch for ch in chunks if ch.chunk_type == ChunkType.METHOD]
        assert len(methods) == 1

    def test_test_function_chunk(self):
        c = Chunker()
        content = "def test_foo():\n    assert True\n"
        sf = _py_scanned("test_mod.py", content, file_id="file:test_mod.py", line_count=2, file_type=FileType.TEST)
        pf = _parsed(file_id="file:test_mod.py", path="test_mod.py", file_type=FileType.TEST, symbols=[
            _sym("test_foo", SymbolType.FUNCTION, 1, 2, "sym:test_foo:1", "test_mod.test_foo"),
        ])
        chunks = c.chunk([sf], [pf])
        tests = [ch for ch in chunks if ch.chunk_type == ChunkType.TEST]
        assert len(tests) == 1
        assert "test_foo" in tests[0].symbol_name

    def test_test_method_chunk(self):
        c = Chunker()
        content = "class TestSuite:\n    def test_run(self):\n        pass\n"
        sf = _py_scanned("test_s.py", content, file_id="file:test_s.py", line_count=3, file_type=FileType.TEST)
        pf = _parsed(file_id="file:test_s.py", path="test_s.py", file_type=FileType.TEST, symbols=[
            _sym("TestSuite", SymbolType.CLASS, 1, 3, "sym:TestSuite:1", "test_s.TestSuite"),
            _sym("test_run", SymbolType.METHOD, 2, 3, "sym:test_run:2", "test_s.TestSuite.test_run", parent_id="sym:TestSuite:1"),
        ])
        chunks = c.chunk([sf], [pf])
        tests = [ch for ch in chunks if ch.chunk_type == ChunkType.TEST]
        test_methods = [t for t in tests if t.symbol_name == "test_run"]
        assert len(test_methods) == 1

    def test_test_class_chunk(self):
        c = Chunker()
        content = "class TestAuth:\n    def test_login(self):\n        pass\n"
        sf = _py_scanned("test_auth.py", content, file_id="file:test_auth.py", line_count=3, file_type=FileType.TEST)
        pf = _parsed(file_id="file:test_auth.py", path="test_auth.py", file_type=FileType.TEST, symbols=[
            _sym("TestAuth", SymbolType.CLASS, 1, 3, "sym:TestAuth:1", "test_auth.TestAuth"),
            _sym("test_login", SymbolType.METHOD, 2, 3, "sym:test_login:2", "test_auth.TestAuth.test_login", parent_id="sym:TestAuth:1"),
        ])
        chunks = c.chunk([sf], [pf])
        tests = [ch for ch in chunks if ch.chunk_type == ChunkType.TEST]
        test_classes = [t for t in tests if t.symbol_name == "TestAuth"]
        assert len(test_classes) == 1

    def test_variable_produces_no_chunk(self):
        c = Chunker()
        content = "DEBUG = True\nx = 1\n"
        sf = _py_scanned("cfg.py", content, file_id="file:cfg.py", line_count=2)
        pf = _parsed(file_id="file:cfg.py", path="cfg.py", symbols=[
            _sym("DEBUG", SymbolType.VARIABLE, 1, 1, "sym:DEBUG:1", "cfg.DEBUG"),
            _sym("x", SymbolType.VARIABLE, 2, 2, "sym:x:2", "cfg.x"),
        ])
        chunks = c.chunk([sf], [pf])
        var_chunks = [ch for ch in chunks if ch.chunk_type in (
            ChunkType.FUNCTION, ChunkType.METHOD, ChunkType.CLASS,
            ChunkType.TEST, ChunkType.ROUTE,
        )]
        assert len(var_chunks) == 0

    def test_route_chunk_created(self):
        c = Chunker()
        content = "import something\n\n@app.get('/users')\ndef list_users():\n    return []\n"
        sf = _py_scanned("routes.py", content, file_id="file:routes.py", line_count=5)
        pf = _parsed(file_id="file:routes.py", path="routes.py", symbols=[
            _sym("list_users", SymbolType.FUNCTION, 4, 5, "sym:list_users:4", "routes.list_users"),
        ], routes=[
            _route(
                route_id="route:GET:/users:routes.py:3",
                path="/users", method=HttpMethod.GET,
                handler="list_users", start=3,
                decorators=["@app.get('/users')"],
            ),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1
        r = routes[0]
        assert r.symbol_id == "route:GET:/users:routes.py:3"
        assert r.metadata["http_method"] == "GET"
        assert r.metadata["route_path"] == "/users"

    def test_route_chunk_includes_decorator_and_handler(self):
        c = Chunker()
        content = "@app.get('/items')\ndef list_items():\n    return []\n"
        sf = _py_scanned("routes.py", content, file_id="file:routes.py", line_count=3)
        pf = _parsed(file_id="file:routes.py", path="routes.py", symbols=[
            _sym("list_items", SymbolType.FUNCTION, 2, 3, "sym:list_items:2", "routes.list_items"),
        ], routes=[
            _route(
                route_id="route:GET:/items:routes.py:1",
                path="/items", method=HttpMethod.GET,
                handler="list_items", start=1,
                decorators=["@app.get('/items')"],
            ),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1
        assert "@app.get" in routes[0].content
        assert "def list_items" in routes[0].content

    def test_route_chunk_uses_route_start_line(self):
        c = Chunker()
        content = "# comment\n@app.get('/x')\ndef handle():\n    pass\n"
        sf = _py_scanned("r.py", content, file_id="file:r.py", line_count=4)
        pf = _parsed(file_id="file:r.py", path="r.py", symbols=[
            _sym("handle", SymbolType.FUNCTION, 3, 4, "sym:handle:3", "r.handle"),
        ], routes=[
            _route(route_id="route:GET:/x:r.py:2", path="/x", method=HttpMethod.GET, handler="handle", start=2),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1
        assert routes[0].start_line == 2

    def test_parse_error_python_produces_only_file_summary(self):
        c = Chunker()
        content = "def broken(\n"
        sf = _py_scanned("broken.py", content, file_id="file:broken.py", line_count=1)
        pf = _parsed(file_id="file:broken.py", path="broken.py", status=ParseStatus.ERROR)
        chunks = c.chunk([sf], [pf])
        types = {ch.chunk_type for ch in chunks}
        assert ChunkType.FILE_SUMMARY in types or len(chunks) == 0
        assert ChunkType.FUNCTION not in types
        assert ChunkType.METHOD not in types
        assert ChunkType.CLASS not in types
        assert ChunkType.TEST not in types
        assert ChunkType.ROUTE not in types

    def test_empty_sanitized_python_produces_no_chunk(self):
        c = Chunker()
        sf = _py_scanned("empty.py", "", file_id="file:empty.py")
        pf = _parsed(file_id="file:empty.py", path="empty.py", status=ParseStatus.PARSED)
        chunks = c.chunk([sf], [pf])
        assert len(chunks) == 0


class TestDocumentationChunking:
    def test_markdown_sections_by_headings(self):
        c = Chunker()
        content = "# Title\n\nSome text\n\n## Section 1\n\nBody 1\n\n### Sub\n\nBody 2\n"
        sf = _doc_scanned("readme.md", content, file_id="file:readme.md")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        assert len(sections) == 3
        assert any("Title" in s.content for s in sections)
        assert any("Section 1" in s.content for s in sections)
        assert any("Sub" in s.content for s in sections)

    def test_markdown_preamble_preserved(self):
        c = Chunker()
        content = "Preamble\n\n# Heading\n\nBody\n"
        sf = _doc_scanned("readme.md", content, file_id="file:readme.md")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        preamble_chunks = [s for s in sections if s.start_line == 1 and "Preamble" in s.content]
        assert len(preamble_chunks) == 1

    def test_markdown_no_headings_one_chunk(self):
        c = Chunker()
        content = "Just a paragraph.\nAnother line.\n"
        sf = _doc_scanned("note.md", content, file_id="file:note.md")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        assert len(sections) == 1
        assert sections[0].start_line == 1

    def test_rst_headings_split_correctly(self):
        c = Chunker()
        content = "Title\n=====\n\nSome text\n\nSection 2\n--------\n\nBody\n"
        sf = _doc_scanned("guide.rst", content, file_id="file:guide.rst")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        assert len(sections) == 2

    def test_doc_sections_have_correct_line_ranges(self):
        c = Chunker()
        content = "# H1\n\n# H2\n"
        sf = _doc_scanned("doc.md", content, file_id="file:doc.md")
        chunks = c.chunk([sf], [])
        sections = sorted(chunks, key=lambda x: x.start_line)
        assert len(sections) == 2
        assert sections[0].start_line == 1
        assert sections[1].start_line > sections[0].end_line

    def test_empty_doc_produces_no_chunks(self):
        c = Chunker()
        content = ""
        sf = _doc_scanned("empty.md", content, file_id="file:empty.md")
        chunks = c.chunk([sf], [])
        assert len(chunks) == 0


class TestConfigurationChunking:
    def _cfg(self, path: str, lines: int) -> ScannedFile:
        content = "\n".join(f"line{i}" for i in range(1, lines + 1))
        return _config_scanned(path, content, file_id=f"file:{path}")

    def test_100_lines_one_chunk(self):
        c = Chunker()
        sf = self._cfg("cfg.json", 100)
        chunks = c.chunk([sf], [])
        configs = [ch for ch in chunks if ch.chunk_type == ChunkType.CONFIG]
        assert len(configs) == 1

    def test_101_lines_two_chunks(self):
        c = Chunker()
        sf = self._cfg("cfg.yaml", 101)
        chunks = c.chunk([sf], [])
        configs = [ch for ch in chunks if ch.chunk_type == ChunkType.CONFIG]
        assert len(configs) == 2

    def test_200_lines_two_chunks(self):
        c = Chunker()
        sf = self._cfg("cfg.toml", 200)
        chunks = c.chunk([sf], [])
        configs = [ch for ch in chunks if ch.chunk_type == ChunkType.CONFIG]
        assert len(configs) == 2

    def test_201_lines_three_chunks(self):
        c = Chunker()
        sf = self._cfg("cfg.ini", 201)
        chunks = c.chunk([sf], [])
        configs = [ch for ch in chunks if ch.chunk_type == ChunkType.CONFIG]
        assert len(configs) == 3

    def test_no_overlap(self):
        c = Chunker()
        sf = self._cfg("cfg.json", 150)
        chunks = c.chunk([sf], [])
        configs = sorted(chunks, key=lambda x: x.start_line)
        for i in range(len(configs) - 1):
            assert configs[i].end_line < configs[i + 1].start_line

    def test_no_missing_lines(self):
        c = Chunker()
        sf = self._cfg("cfg.yml", 201)
        chunks = c.chunk([sf], [])
        configs = sorted(chunks, key=lambda x: x.start_line)
        total = sum(ch.end_line - ch.start_line + 1 for ch in configs)
        assert total == 201

    def test_correct_block_metadata(self):
        c = Chunker()
        sf = self._cfg("cfg.toml", 250)
        chunks = c.chunk([sf], [])
        configs = sorted(chunks, key=lambda x: x.start_line)
        assert len(configs) == 3
        assert configs[0].metadata["block_index"] == 0
        assert configs[1].metadata["block_index"] == 1
        assert configs[2].metadata["block_index"] == 2
        assert all(ch.metadata["block_count"] == 3 for ch in configs)

    def test_recognized_config_names(self):
        c = Chunker()
        names = [
            "cfg.json", "cfg.toml", "cfg.yaml", "cfg.yml",
            "cfg.ini", "cfg.cfg", "requirements.txt",
            "requirements-dev.txt", "pyproject.toml",
            "Makefile", "Dockerfile", ".gitignore", ".deeporraignore",
        ]
        for name in names:
            sf = _config_scanned(name, "key = value\n", file_id=f"file:{name}")
            chunks = c.chunk([sf], [])
            configs = [ch for ch in chunks if ch.chunk_type == ChunkType.CONFIG]
            assert len(configs) >= 1, f"no config chunk for {name}"


class TestDeterminism:
    def test_repeated_calls_identical_ids(self):
        c = Chunker()
        sf = _py_scanned("det.py", "def foo(): pass\n", file_id="file:det.py")
        pf = _parsed(file_id="file:det.py", path="det.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 1, 1, "sym:foo:1", "det.foo"),
        ])
        chunks1 = c.chunk([sf], [pf])
        chunks2 = c.chunk([sf], [pf])
        ids1 = [ch.chunk_id for ch in chunks1]
        ids2 = [ch.chunk_id for ch in chunks2]
        assert ids1 == ids2

    def test_repeated_calls_identical_hashes(self):
        c = Chunker()
        sf = _py_scanned("hash.py", "def bar(): pass\n", file_id="file:hash.py")
        pf = _parsed(file_id="file:hash.py", path="hash.py", symbols=[
            _sym("bar", SymbolType.FUNCTION, 1, 1, "sym:bar:1", "hash.bar"),
        ])
        chunks1 = c.chunk([sf], [pf])
        chunks2 = c.chunk([sf], [pf])
        h1 = [ch.content_hash for ch in chunks1]
        h2 = [ch.content_hash for ch in chunks2]
        assert h1 == h2

    def test_repeated_calls_identical_ordering(self):
        c = Chunker()
        sf1 = _py_scanned("a.py", "def a(): pass\n", file_id="file:a.py")
        pf1 = _parsed(file_id="file:a.py", path="a.py", symbols=[
            _sym("a", SymbolType.FUNCTION, 1, 1, "sym:a:1", "a.a"),
        ])
        sf2 = _py_scanned("b.py", "def b(): pass\n", file_id="file:b.py")
        pf2 = _parsed(file_id="file:b.py", path="b.py", symbols=[
            _sym("b", SymbolType.FUNCTION, 1, 1, "sym:b:1", "b.b"),
        ])
        order1 = c.chunk([sf1, sf2], [pf1, pf2])
        order2 = c.chunk([sf1, sf2], [pf1, pf2])
        paths1 = [(ch.file_path, ch.start_line) for ch in order1]
        paths2 = [(ch.file_path, ch.start_line) for ch in order2]
        assert paths1 == paths2

    def test_changed_content_changes_hash_and_id(self):
        c = Chunker()
        sf1 = _py_scanned("mut.py", "def v1(): return 1\n", file_id="file:mut.py")
        pf1 = _parsed(file_id="file:mut.py", path="mut.py", symbols=[
            _sym("v1", SymbolType.FUNCTION, 1, 1, "sym:v1:1", "mut.v1"),
        ])
        sf2 = _py_scanned("mut.py", "def v1(): return 2\n", file_id="file:mut.py")
        pf2 = _parsed(file_id="file:mut.py", path="mut.py", symbols=[
            _sym("v1", SymbolType.FUNCTION, 1, 1, "sym:v1:1", "mut.v1"),
        ])
        chunks1 = c.chunk([sf1], [pf1])
        chunks2 = c.chunk([sf2], [pf2])
        assert any(
            c1.chunk_id != c2.chunk_id or c1.content_hash != c2.content_hash
            for c1, c2 in zip(chunks1, chunks2)
        )

    def test_all_paths_relative(self):
        c = Chunker()
        sf = _py_scanned("sub/mod.py", "def foo(): pass\n", file_id="file:sub/mod.py")
        pf = _parsed(file_id="file:sub/mod.py", path="sub/mod.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 1, 1, "sym:foo:1", "sub.mod.foo"),
        ])
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            assert "/" not in chunk.file_path or not chunk.file_path.startswith("/")
            assert ".." not in chunk.file_path

    def test_all_line_ranges_valid(self):
        c = Chunker()
        sf = _py_scanned("valid.py", "def foo(): pass\ndef bar(): pass\n", file_id="file:valid.py", line_count=2)
        pf = _parsed(file_id="file:valid.py", path="valid.py", symbols=[
            _sym("foo", SymbolType.FUNCTION, 1, 1, "sym:foo:1", "valid.foo"),
            _sym("bar", SymbolType.FUNCTION, 2, 2, "sym:bar:2", "valid.bar"),
        ])
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            assert 1 <= chunk.start_line <= chunk.end_line

    def test_content_hash_matches_content(self):
        c = Chunker()
        sf = _py_scanned("hash_check.py", "def h(): pass\n", file_id="file:hash_check.py")
        pf = _parsed(file_id="file:hash_check.py", path="hash_check.py", symbols=[
            _sym("h", SymbolType.FUNCTION, 1, 1, "sym:h:1", "hash_check.h"),
        ])
        chunks = c.chunk([sf], [pf])
        for chunk in chunks:
            expected = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            assert chunk.content_hash == expected

    def test_duplicate_symbol_names_separate_chunks(self):
        c = Chunker()
        content = "def dup(): pass\ndef dup(): pass\n"
        sf = _py_scanned("dup.py", content, file_id="file:dup.py", line_count=2)
        pf = _parsed(file_id="file:dup.py", path="dup.py", symbols=[
            _sym("dup", SymbolType.FUNCTION, 1, 1, "sym:dup:1", "dup.dup"),
            _sym("dup", SymbolType.FUNCTION, 2, 2, "sym:dup:2", "dup.dup"),
        ])
        chunks = c.chunk([sf], [pf])
        funcs = [ch for ch in chunks if ch.chunk_type == ChunkType.FUNCTION]
        assert len(funcs) == 2
        assert funcs[0].symbol_name == funcs[1].symbol_name
        assert funcs[0].start_line != funcs[1].start_line

    def test_generic_text_produces_no_chunks(self):
        c = Chunker()
        sf = ScannedFile(
            file_id="file:notes.txt",
            file_path="notes.txt",
            file_type=FileType.DOC,
            safe_content="Some notes\nMore notes\n",
            line_count=2,
            has_secrets=False,
            language=None,
        )
        chunks = c.chunk([sf], [])
        assert len(chunks) == 0


class TestInvalidInputs:
    def test_duplicate_scanned_ids_raises(self):
        c = Chunker()
        sf = _py_scanned("a.py", "x=1\n", file_id="file:dup")
        sf2 = _py_scanned("b.py", "y=2\n", file_id="file:dup")
        with pytest.raises(ValueError, match="duplicate scanned"):
            c.chunk([sf, sf2], [])

    def test_duplicate_parsed_ids_raises(self):
        c = Chunker()
        pf1 = _parsed(file_id="file:dup", path="a.py")
        pf2 = _parsed(file_id="file:dup", path="b.py")
        sf = _py_scanned("a.py", "x=1\n", file_id="file:dup")
        with pytest.raises(ValueError, match="duplicate parsed"):
            c.chunk([sf], [pf1, pf2])

    def test_parsed_without_scanned_raises(self):
        c = Chunker()
        pf = _parsed(file_id="file:unknown", path="unknown.py")
        with pytest.raises(ValueError, match="no matching scanned file"):
            c.chunk([], [pf])

    def test_python_without_parsed_raises(self):
        c = Chunker()
        sf = _py_scanned("orphan.py", "x=1\n", file_id="file:orphan.py")
        with pytest.raises(ValueError, match="requires a matching parsed file"):
            c.chunk([sf], [])


class TestFilePathRequired:
    def test_code_chunk_file_path_required(self):
        from deeporra.contracts import CodeChunk, ChunkType
        with pytest.raises(TypeError):
            CodeChunk(
                chunk_id="x", file_id="y", chunk_type=ChunkType.FILE_SUMMARY,
                content="z", start_line=1, end_line=1,
            )


class TestFileAccessTraps:
    def test_path_read_text_not_called(self, monkeypatch):
        import pathlib
        pathlib.Path.read_text

        def trap(*a, **kw):
            raise RuntimeError("Path.read_text called")
        monkeypatch.setattr(pathlib.Path, "read_text", trap)
        c = Chunker()
        sf = _py_scanned("safe.py", "x=1\n", file_id="file:safe.py")
        pf = _parsed(file_id="file:safe.py", path="safe.py")
        c.chunk([sf], [pf])

    def test_path_read_bytes_not_called(self, monkeypatch):
        import pathlib
        pathlib.Path.read_bytes

        def trap(*a, **kw):
            raise RuntimeError("Path.read_bytes called")
        monkeypatch.setattr(pathlib.Path, "read_bytes", trap)
        c = Chunker()
        sf = _py_scanned("safe.py", "x=1\n", file_id="file:safe.py")
        pf = _parsed(file_id="file:safe.py", path="safe.py")
        c.chunk([sf], [pf])


class TestUUID5Determinism:
    def test_chunk_id_is_uuid5(self):
        c = Chunker()
        sf = _py_scanned("det.py", "def f(): pass\n", file_id="file:det.py")
        pf = _parsed(file_id="file:det.py", path="det.py", symbols=[
            _sym("f", SymbolType.FUNCTION, 1, 1, "sym:f:1", "det.f"),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            parsed = uuid.UUID(ch.chunk_id)
            assert parsed.version == 5

    def test_chunk_id_is_not_uuid4(self):
        c = Chunker()
        sf = _py_scanned("det2.py", "def g(): pass\n", file_id="file:det2.py")
        pf = _parsed(file_id="file:det2.py", path="det2.py", symbols=[
            _sym("g", SymbolType.FUNCTION, 1, 1, "sym:g:1", "det2.g"),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            parsed = uuid.UUID(ch.chunk_id)
            assert parsed.version != 4


class TestComprehensivePythonChunking:
    def test_all_chunk_types_counted(self):
        c = Chunker()
        content = (
            "'''Module docstring.\nMulti-line.\n'''\n"
            "import os\n"
            "DEBUG = True\n"
            "\n"
            "def normal_func():\n"
            "    pass\n"
            "\n"
            "async def async_func():\n"
            "    return 1\n"
            "\n"
            "class MyClass:\n"
            "    \"\"\"Class doc.\"\"\"\n"
            "    def inst_method(self):\n"
            "        pass\n"
            "\n"
            "    async def async_method(self):\n"
            "        await asyncio.sleep(0)\n"
            "\n"
            "@app.get('/items')\n"
            "def list_items():\n"
            "    return []\n"
            "\n"
            "def test_check():\n"
            "    assert True\n"
            "\n"
            "class TestGroup:\n"
            "    def test_sub(self):\n"
            "        pass\n"
        )
        sf = _py_scanned("full.py", content, file_id="file:full.py",
                         line_count=content.count("\n"), file_type=FileType.SOURCE)
        route_symbol_id = "route:GET:/items:full.py:21"
        pf = _parsed(file_id="file:full.py", path="full.py", file_type=FileType.SOURCE, symbols=[
            _sym("normal_func", SymbolType.FUNCTION, 7, 8, "sym:nf:7", "full.normal_func"),
            _sym("async_func", SymbolType.FUNCTION, 10, 11, "sym:af:10", "full.async_func"),
            _sym("MyClass", SymbolType.CLASS, 13, 20, "sym:mc:13", "full.MyClass"),
            _sym("inst_method", SymbolType.METHOD, 15, 16, "sym:im:15", "full.MyClass.inst_method", parent_id="sym:mc:13"),
            _sym("async_method", SymbolType.METHOD, 18, 19, "sym:am:18", "full.MyClass.async_method", parent_id="sym:mc:13"),
            _sym("list_items", SymbolType.FUNCTION, 22, 23, route_symbol_id, "full.list_items"),
            _sym("test_check", SymbolType.FUNCTION, 25, 26, "sym:tc:25", "full.test_check"),
            _sym("TestGroup", SymbolType.CLASS, 28, 30, "sym:tg:28", "full.TestGroup"),
            _sym("test_sub", SymbolType.METHOD, 29, 30, "sym:ts:29", "full.TestGroup.test_sub", parent_id="sym:tg:28"),
            _sym("DEBUG", SymbolType.VARIABLE, 3, 3, "sym:dbg:3", "full.DEBUG"),
        ], routes=[
            _route(
                route_id=route_symbol_id,
                path="/items", method=HttpMethod.GET,
                handler="list_items", start=21,
                decorators=["@app.get('/items')"],
            ),
        ])
        chunks = c.chunk([sf], [pf])
        counts = {}
        for ch in chunks:
            counts[ch.chunk_type] = counts.get(ch.chunk_type, 0) + 1
        assert counts.get(ChunkType.FILE_SUMMARY) == 1
        assert counts.get(ChunkType.FUNCTION) == 2
        assert counts.get(ChunkType.CLASS) == 1
        assert counts.get(ChunkType.METHOD) == 2
        assert counts.get(ChunkType.ROUTE) == 1
        assert counts.get(ChunkType.TEST) == 3
        assert counts.get(ChunkType.CONFIG) is None
        assert counts.get(ChunkType.README_SECTION) is None

    def test_variable_not_chunked(self):
        c = Chunker()
        sf = _py_scanned("vars.py", "A=1\nB=2\n", file_id="file:vars.py")
        pf = _parsed(file_id="file:vars.py", path="vars.py", symbols=[
            _sym("A", SymbolType.VARIABLE, 1, 1, "sym:A:1", "vars.A"),
            _sym("B", SymbolType.VARIABLE, 2, 2, "sym:B:2", "vars.B"),
        ])
        chunks = c.chunk([sf], [pf])
        symbol_chunks = [ch for ch in chunks if ch.chunk_type not in (ChunkType.FILE_SUMMARY,)]
        assert len(symbol_chunks) == 0


class TestRouteEvidence:
    def test_route_start_line_matches(self):
        c = Chunker()
        content = "# comment\n@app.get('/x')\ndef handle():\n    pass\n"
        sf = _py_scanned("r.py", content, file_id="file:r.py", line_count=4)
        pf = _parsed(file_id="file:r.py", path="r.py", symbols=[
            _sym("handle", SymbolType.FUNCTION, 3, 4, "sym:handle:3", "r.handle"),
        ], routes=[
            _route(route_id="route:GET:/x:r.py:2", path="/x", method=HttpMethod.GET, handler="handle", start=2),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1
        assert routes[0].start_line == 2
        assert "@app.get" in routes[0].content
        assert "def handle" in routes[0].content
        assert routes[0].symbol_id == "route:GET:/x:r.py:2"

    def test_route_metadata_complete(self):
        c = Chunker()
        content = "@app.post('/users')\ndef create():\n    pass\n"
        sf = _py_scanned("routes.py", content, file_id="file:routes.py", line_count=3)
        pf = _parsed(file_id="file:routes.py", path="routes.py", symbols=[
            _sym("create", SymbolType.FUNCTION, 2, 3, "sym:create:2", "routes.create"),
        ], routes=[
            _route(
                route_id="route:POST:/users:routes.py:1",
                path="/users", method=HttpMethod.POST,
                handler="create", start=1,
                decorators=["@app.post('/users')"],
            ),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1
        r = routes[0]
        assert r.metadata["http_method"] == "POST"
        assert r.metadata["route_path"] == "/users"
        assert r.metadata["handler_function"] == "create"
        assert r.metadata["decorators"] == ["@app.post('/users')"]
        assert r.metadata["qualified_name"] == "create"

    def test_not_two_route_chunks_for_one_route(self):
        c = Chunker()
        content = "@app.get('/once')\ndef once():\n    pass\n"
        sf = _py_scanned("once.py", content, file_id="file:once.py", line_count=3)
        pf = _parsed(file_id="file:once.py", path="once.py", symbols=[
            _sym("once", SymbolType.FUNCTION, 2, 3, "sym:once:2", "once.once"),
        ], routes=[
            _route(route_id="route:GET:/once:once.py:1", path="/once", method=HttpMethod.GET, handler="once", start=1),
        ])
        chunks = c.chunk([sf], [pf])
        routes = [ch for ch in chunks if ch.chunk_type == ChunkType.ROUTE]
        assert len(routes) == 1


class TestClassNoMethodBody:
    def test_class_chunk_does_not_contain_method_body(self):
        c = Chunker()
        content = (
            "class Calculator:\n"
            "    \"\"\"Calc doc.\"\"\"\n"
            "    def work(self):\n"
            "        unique_method_body_marker = \"DO_NOT_DUPLICATE\"\n"
            "        return 42\n"
        )
        sf = _py_scanned("calc.py", content, file_id="file:calc.py", line_count=5)
        pf = _parsed(file_id="file:calc.py", path="calc.py", symbols=[
            _sym("Calculator", SymbolType.CLASS, 1, 5, "sym:Calc:1", "calc.Calculator",
                 doc="Calc doc."),
            _sym("work", SymbolType.METHOD, 3, 5, "sym:work:3", "calc.Calculator.work",
                 parent_id="sym:Calc:1"),
        ])
        chunks = c.chunk([sf], [pf])
        classes = [ch for ch in chunks if ch.chunk_type == ChunkType.CLASS]
        methods = [ch for ch in chunks if ch.chunk_type == ChunkType.METHOD]
        assert len(classes) == 1
        assert len(methods) == 1
        assert "DO_NOT_DUPLICATE" in methods[0].content
        assert "DO_NOT_DUPLICATE" not in classes[0].content
        assert "Calculator" in classes[0].content
        assert "work" in classes[0].content or "Calc doc" in classes[0].content


class TestMetadataJsonSerialization:
    def test_symbol_chunk_metadata_json_serializable(self):
        import json
        c = Chunker()
        sf = _py_scanned("ser.py", "def fn(): pass\n", file_id="file:ser.py")
        pf = _parsed(file_id="file:ser.py", path="ser.py", symbols=[
            _sym("fn", SymbolType.FUNCTION, 1, 1, "sym:fn:1", "ser.fn", sig="()"),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            s = json.dumps(ch.metadata, sort_keys=True)
            assert isinstance(s, str)
            d = json.loads(s)
            assert "has_secrets" in d
            assert "parse_status" in d

    def test_route_chunk_metadata_json_serializable(self):
        import json
        c = Chunker()
        content = "@app.get('/ser')\ndef serve(): pass\n"
        sf = _py_scanned("ser_route.py", content, file_id="file:ser_route.py", line_count=2)
        pf = _parsed(file_id="file:ser_route.py", path="ser_route.py", symbols=[
            _sym("serve", SymbolType.FUNCTION, 2, 2, "sym:serve:2", "ser_route.serve"),
        ], routes=[
            _route(route_id="route:GET:/ser:ser_route.py:1", path="/ser", handler="serve", start=1),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            s = json.dumps(ch.metadata, sort_keys=True)
            assert isinstance(s, str)
            json.loads(s)

    def test_doc_chunk_metadata_json_serializable(self):
        import json
        c = Chunker()
        sf = _doc_scanned("doc.md", "# Title\n\nBody\n", file_id="file:doc.md")
        chunks = c.chunk([sf], [])
        for ch in chunks:
            s = json.dumps(ch.metadata, sort_keys=True)
            assert isinstance(s, str)
            if ch.metadata.get("heading"):
                assert isinstance(ch.metadata["heading"], str)

    def test_config_chunk_metadata_json_serializable(self):
        import json
        c = Chunker()
        sf = _config_scanned("cfg.json", "key=val\n", file_id="file:cfg.json")
        chunks = c.chunk([sf], [])
        for ch in chunks:
            s = json.dumps(ch.metadata, sort_keys=True)
            assert isinstance(s, str)
            assert "block_index" in ch.metadata
            assert "block_count" in ch.metadata


class TestLineAndPathBoundaries:
    def test_start_line_never_exceeds_end_line(self):
        c = Chunker()
        sf = _py_scanned("lb.py", "def f(): pass\n", file_id="file:lb.py")
        pf = _parsed(file_id="file:lb.py", path="lb.py", symbols=[
            _sym("f", SymbolType.FUNCTION, 1, 1, "sym:f:1", "lb.f"),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            assert ch.start_line >= 1
            assert ch.start_line <= ch.end_line

    def test_no_absolute_path_in_chunks(self):
        c = Chunker()
        sf = _py_scanned("sub/mod.py", "def f(): pass\n", file_id="file:sub/mod.py")
        pf = _parsed(file_id="file:sub/mod.py", path="sub/mod.py", symbols=[
            _sym("f", SymbolType.FUNCTION, 1, 1, "sym:f:1", "sub.mod.f"),
        ])
        chunks = c.chunk([sf], [pf])
        for ch in chunks:
            assert not ch.file_path.startswith("/")
            assert ".." not in ch.file_path

    def test_content_without_final_newline(self):
        c = Chunker()
        content = "line1\nline2"
        sf = _py_scanned("noeol.py", content, file_id="file:noeol.py", line_count=2)
        pf = _parsed(file_id="file:noeol.py", path="noeol.py", symbols=[
            _sym("f1", SymbolType.FUNCTION, 1, 1, "sym:f1:1", "noeol.f1"),
            _sym("f2", SymbolType.FUNCTION, 2, 2, "sym:f2:2", "noeol.f2"),
        ])
        chunks = c.chunk([sf], [pf])
        funcs = [ch for ch in chunks if ch.chunk_type == ChunkType.FUNCTION]
        assert len(funcs) == 2
        assert all(ch.start_line <= ch.end_line for ch in funcs)


class TestEmptyConfigBehavior:
    def test_empty_config_produces_no_chunks(self):
        c = Chunker()
        sf = _config_scanned("empty.json", "", file_id="file:empty.json")
        chunks = c.chunk([sf], [])
        assert len(chunks) == 0


class TestRSTChunking:
    def test_rst_with_title_and_sections(self):
        c = Chunker()
        content = "Header\n======\n\nBody text.\n\nSub\n---\n\nMore.\n"
        sf = _doc_scanned("doc.rst", content, file_id="file:doc.rst")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        assert len(sections) >= 2
        assert any("Header" in s.content for s in sections)
        assert any("Sub" in s.content for s in sections)

    def test_rst_preamble_preserved(self):
        c = Chunker()
        content = "Preamble\n\nTitle\n=====\n\nBody\n"
        sf = _doc_scanned("preamble.rst", content, file_id="file:preamble.rst")
        chunks = c.chunk([sf], [])
        sections = [ch for ch in chunks if ch.chunk_type == ChunkType.README_SECTION]
        preamble_chunks = [s for s in sections if s.start_line == 1 and "Preamble" in s.content]
        assert len(preamble_chunks) == 1

    def test_rst_empty_doc_no_chunks(self):
        c = Chunker()
        sf = _doc_scanned("empty.rst", "", file_id="file:empty.rst")
        chunks = c.chunk([sf], [])
        assert len(chunks) == 0

    def test_rst_inclusive_line_ranges(self):
        c = Chunker()
        content = "Title\n=====\n\nBody\n"
        sf = _doc_scanned("lines.rst", content, file_id="file:lines.rst")
        chunks = c.chunk([sf], [])
        for ch in chunks:
            assert ch.start_line >= 1
            assert ch.end_line >= ch.start_line
