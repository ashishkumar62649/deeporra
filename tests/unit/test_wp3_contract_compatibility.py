"""Contract compatibility tests — verify WP3 modules satisfy canonical contracts."""

import ast
import os
import uuid
import pytest

from fcode.contracts import (
    ChunkType,
    Confidence,
    FileType,
    GraphNodeType,
    GraphRelation,
    HttpMethod,
    ParseStatus,
    SymbolType,
)
from fcode.contracts import (
    GraphBuildResult,
    GraphEdgeInput,
    GraphNodeInput,
    ParsedFile,
    ParsedImport,
    ParsedRoute,
    ParsedSymbol,
    ScanResult,
    ScannedFile,
    SkippedFileDiagnostic,
)
from fcode.contracts.interfaces import (
    GraphBuilderProtocol,
    PythonParserProtocol,
    ScannerProtocol,
)


class TestEnumsAreCanonical:
    def test_no_stale_enums(self):
        members = {e.name for e in FileType}
        assert "PYTHON" not in members
        assert "MARKDOWN" not in members
        assert "FAILED" not in {e.name for e in ParseStatus}
        assert "SKIPPED" not in {e.name for e in ParseStatus}
        assert "SYMBOL" not in {e.name for e in ChunkType}
        assert "CHUNK" not in {e.name for e in GraphNodeType}
        assert "CONTAINS" not in {e.name for e in GraphRelation}
        assert "USES" not in {e.name for e in GraphRelation}

    def test_graph_node_types_have_required_members(self):
        required = {"FILE", "FUNCTION", "CLASS", "METHOD", "ROUTE", "IMPORT", "TEST"}
        assert required.issubset({e.name for e in GraphNodeType})

    def test_graph_relations_have_required_members(self):
        required = {"DEFINES", "IMPORTS", "INHERITS", "CALLS", "TESTS", "HANDLES_ROUTE"}
        assert required.issubset({e.name for e in GraphRelation})


class TestProtocolCompliance:
    def test_scanner_public_method_matches_protocol(self):
        from fcode.scanner.file_scanner import scan
        assert callable(scan)
        import inspect
        sig = inspect.signature(scan)
        params = list(sig.parameters.keys())
        assert "repo" in params
        assert "config" in params

    def test_parser_public_method_matches_protocol(self):
        from fcode.parser.python_ast import parse
        assert callable(parse)
        import inspect
        sig = inspect.signature(parse)
        params = list(sig.parameters.keys())
        assert "file" in params

    def test_graph_builder_public_method_matches_protocol(self):
        from fcode.graph.graph_builder import build
        assert callable(build)
        import inspect
        sig = inspect.signature(build)
        params = list(sig.parameters.keys())
        assert "parsed_files" in params


class TestScannerContract:
    def test_scanner_returns_real_scanresult(self):
        from fcode.scanner.file_scanner import scan
        from fcode.contracts import FCodeConfig, RepoInput
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = scan(RepoInput(repo_path=tmp), FCodeConfig(repo_path=tmp))
            assert isinstance(result, ScanResult)

    def test_scanner_returns_real_scannedfile(self):
        from fcode.scanner.file_scanner import scan
        from fcode.contracts import FCodeConfig, RepoInput
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mod.py"), "w") as f:
                f.write("x=1\n")
            result = scan(RepoInput(repo_path=tmp), FCodeConfig(repo_path=tmp))
            assert len(result.files) >= 1
            assert isinstance(result.files[0], ScannedFile)

    def test_no_dynamic_fields_attached_by_scanner(self):
        import tempfile
        from fcode.scanner.file_scanner import scan
        from fcode.contracts import FCodeConfig, RepoInput
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mod.py"), "w") as f:
                f.write("x=1\n")
            result = scan(RepoInput(repo_path=tmp), FCodeConfig(repo_path=tmp))
            for sf in result.files:
                known = {"file_path", "file_type", "size_bytes", "is_binary",
                         "file_id", "absolute_path", "language", "has_secrets",
                         "content_hash", "parse_status", "safe_content", "line_count"}
                for attr in sf.__dataclass_fields__:
                    assert attr in known, f"Unexpected field: {attr}"

    def test_scannedfile_has_safe_content(self):
        sf = ScannedFile(file_path="test.py", safe_content="x=1\n")
        assert hasattr(sf, "safe_content")

    def test_scannedfile_line_count(self):
        sf = ScannedFile(file_path="test.py", safe_content="a\nb\nc\n", line_count=3)
        assert sf.line_count == 3


class TestParserContract:
    def test_parser_accepts_scannedfile(self):
        from fcode.parser.python_ast import parse
        sf = ScannedFile(file_path="mod.py", safe_content="x=1\n",
                         file_type=FileType.SOURCE, content_hash="abc")
        result = parse(sf)
        assert isinstance(result, ParsedFile)

    def test_parser_preserves_file_id(self):
        from fcode.parser.python_ast import parse
        sf = ScannedFile(file_path="mod.py", safe_content="x=1\n",
                         file_type=FileType.SOURCE, content_hash="abc",
                         file_id="file:mod.py")
        result = parse(sf)
        assert result.file_id == "file:mod.py"

    def test_parser_never_reopens_original_source(self):
        from fcode.parser.python_ast import parse
        import builtins
        original_open = builtins.open
        calls = []
        def tracking_open(*args, **kwargs):
            calls.append(args)
            return original_open(*args, **kwargs)
        import builtins as b
        saved = b.open
        b.open = tracking_open
        try:
            sf = ScannedFile(file_path="nonexistent.py", safe_content="x=1\n",
                             file_type=FileType.SOURCE, content_hash="abc")
            result = parse(sf)
            file_calls = [c for c in calls if "nonexistent" in str(c)]
            assert len(file_calls) == 0
        finally:
            b.open = saved

    def test_syntax_failure_returns_error_status(self):
        from fcode.parser.python_ast import parse
        sf = ScannedFile(file_path="bad.py", safe_content="def foo(:\n",
                         file_type=FileType.SOURCE, content_hash="abc")
        result = parse(sf)
        assert result.status == ParseStatus.ERROR

    def test_syntax_failure_empty_lists(self):
        from fcode.parser.python_ast import parse
        sf = ScannedFile(file_path="bad.py", safe_content="def foo(:\n",
                         file_type=FileType.SOURCE, content_hash="abc")
        result = parse(sf)
        assert result.symbols == []
        assert result.imports == []
        assert result.routes == []


class TestSymbolExtraction:
    SRC_FUNC = "def hello():\n    pass\n"
    SRC_ASYNC_FUNC = "async def fetch():\n    pass\n"
    SRC_CLASS = "class MyClass:\n    pass\n"
    SRC_METHOD = "class Foo:\n    def bar(self):\n        pass\n"
    SRC_ASYNC_METHOD = "class Foo:\n    async def bar(self):\n        pass\n"
    SRC_VAR = "x = 42\n"
    SRC_NESTED = "class Outer:\n    class Inner:\n        def method(self): pass\n"

    def _parse(self, code):
        from fcode.parser.python_ast import parse
        sf = ScannedFile(file_path="mod.py", safe_content=code,
                         file_type=FileType.SOURCE, content_hash="abc")
        return parse(sf)

    def test_function_extraction(self):
        pf = self._parse(self.SRC_FUNC)
        funcs = [s for s in pf.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "hello"

    def test_async_function_extraction(self):
        pf = self._parse(self.SRC_ASYNC_FUNC)
        funcs = [s for s in pf.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(funcs) == 1

    def test_class_extraction(self):
        pf = self._parse(self.SRC_CLASS)
        classes = [s for s in pf.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_method_extraction(self):
        pf = self._parse(self.SRC_METHOD)
        methods = [s for s in pf.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "bar"

    def test_async_method_extraction(self):
        pf = self._parse(self.SRC_ASYNC_METHOD)
        methods = [s for s in pf.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 1

    def test_variable_extraction(self):
        pf = self._parse(self.SRC_VAR)
        vars_ = [s for s in pf.symbols if s.symbol_type == SymbolType.VARIABLE]
        assert len(vars_) == 1
        assert vars_[0].name == "x"

    def test_parent_symbol_relationship(self):
        pf = self._parse(self.SRC_NESTED)
        methods = [s for s in pf.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 1
        assert methods[0].parent == "Inner"
        assert methods[0].qualified_name == "Outer.Inner.method"


class TestRouteContract:
    SRC = """
@app.get("/users")
def list_users():
    pass
"""

    def _parse(self, code=None):
        from fcode.parser.python_ast import parse
        src = code or self.SRC
        sf = ScannedFile(file_path="routes.py", safe_content=src,
                         file_type=FileType.SOURCE, content_hash="abc")
        return parse(sf)

    def test_one_route_one_symbol(self):
        pf = self._parse()
        assert len(pf.routes) == 1
        route_syms = [s for s in pf.symbols if s.symbol_type == SymbolType.ROUTE]
        assert len(route_syms) == 1

    def test_shared_uuid(self):
        pf = self._parse()
        assert pf.routes[0].route_id is not None
        route_syms = [s for s in pf.symbols if s.symbol_type == SymbolType.ROUTE]
        assert route_syms[0].symbol_id == pf.routes[0].route_id

    def test_route_symbol_appears_once(self):
        pf = self._parse()
        route_syms = [s for s in pf.symbols if s.symbol_type == SymbolType.ROUTE]
        assert len(route_syms) == 1
        appearances = [s for s in pf.symbols if s.symbol_id == pf.routes[0].route_id]
        assert len(appearances) == 1


class TestGraphContract:
    def _make_pf(self, symbols=None, routes=None, imports=None, file_path="mod.py",
                  file_type=FileType.SOURCE):
        pf = ParsedFile(file_path=file_path, file_type=file_type,
                        status=ParseStatus.PARSED, file_id=f"file:{file_path}")
        if symbols:
            pf.symbols.extend(symbols)
        if routes:
            pf.routes.extend(routes)
        if imports:
            pf.imports.extend(imports)
        return pf

    def _sym(self, name, typ=SymbolType.FUNCTION, **kw):
        kw.setdefault("symbol_id", f"sym:{name}")
        kw.setdefault("start_line", 1)
        kw.setdefault("end_line", 1)
        return ParsedSymbol(name=name, symbol_type=typ, confidence=Confidence.EXTRACTED, **kw)

    def _imp(self, module, names=None, **kw):
        kw.setdefault("line_number", 1)
        return ParsedImport(module_name=module, imported_names=names or [module],
                            confidence=Confidence.EXTRACTED, **kw)

    def _route(self, path, fn, **kw):
        kw.setdefault("route_id", f"route:GET:/{path}:mod.py:1")
        kw.setdefault("start_line", 1)
        return ParsedRoute(route_path=f"/{path}", handler_function=fn,
                           method=HttpMethod.GET, confidence=Confidence.EXTRACTED, **kw)

    def test_canonical_graph_node_types(self):
        from fcode.graph.graph_builder import build
        pf = self._make_pf(symbols=[
            self._sym("foo", SymbolType.FUNCTION),
            self._sym("MyClass", SymbolType.CLASS),
            self._sym("bar", SymbolType.METHOD),
        ])
        result = build([pf])
        types_found = {n.node_type for n in result.nodes}
        assert GraphNodeType.FILE in types_found
        assert GraphNodeType.FUNCTION in types_found
        assert GraphNodeType.CLASS in types_found
        assert GraphNodeType.METHOD in types_found

    def test_test_node_projection(self):
        from fcode.graph.graph_builder import build
        pf = self._make_pf(file_path="test_mod.py", file_type=FileType.TEST,
                           symbols=[self._sym("test_foo", SymbolType.FUNCTION)])
        result = build([pf])
        test_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.TEST]
        assert len(test_nodes) == 1
        fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
        assert len(fn_nodes) == 0

    def test_defines_edge(self):
        from fcode.graph.graph_builder import build
        pf = self._make_pf(symbols=[self._sym("foo", SymbolType.FUNCTION)])
        result = build([pf])
        defines_edges = [e for e in result.edges if e.relation == GraphRelation.DEFINES]
        assert len(defines_edges) >= 1

    def test_imports_edge(self):
        from fcode.graph.graph_builder import build
        pf = self._make_pf(imports=[self._imp("os")])
        result = build([pf])
        imports_edges = [e for e in result.edges if e.relation == GraphRelation.IMPORTS]
        assert len(imports_edges) >= 1

    def test_inherits_edge(self):
        from fcode.graph.graph_builder import build
        base = self._sym("Base", SymbolType.CLASS, symbol_id="sym:Base")
        child = self._sym("Child", SymbolType.CLASS, symbol_id="sym:Child",
                          metadata={"bases": ["Base"]})
        pf = self._make_pf(symbols=[base, child])
        result = build([pf])
        inherits_edges = [e for e in result.edges if e.relation == GraphRelation.INHERITS]
        assert len(inherits_edges) >= 1
        assert inherits_edges[0].source_node_id == "sym:Child"
        assert inherits_edges[0].target_node_id == "sym:Base"

    def test_calls_edge(self):
        from fcode.graph.graph_builder import build
        caller = self._sym("caller", SymbolType.FUNCTION, symbol_id="sym:caller",
                           metadata={"calls": ["callee"]})
        callee = self._sym("callee", SymbolType.FUNCTION, symbol_id="sym:callee")
        pf = self._make_pf(symbols=[caller, callee])
        result = build([pf])
        calls_edges = [e for e in result.edges if e.relation == GraphRelation.CALLS]
        assert len(calls_edges) >= 1
        assert calls_edges[0].source_node_id == "sym:caller"
        assert calls_edges[0].target_node_id == "sym:callee"

    def test_tests_edge(self):
        from fcode.graph.graph_builder import build
        test_fn = self._sym("test_foo", SymbolType.FUNCTION, symbol_id="sym:test_foo")
        target_fn = self._sym("foo", SymbolType.FUNCTION, symbol_id="sym:foo")
        pf = self._make_pf(file_path="test_mod.py", symbols=[test_fn, target_fn])
        result = build([pf])
        tests_edges = [e for e in result.edges if e.relation == GraphRelation.TESTS]
        assert len(tests_edges) >= 1
        assert tests_edges[0].source_node_id == "sym:test_foo"

    def test_handles_route_edge(self):
        from fcode.graph.graph_builder import build
        rid = "route:GET:/users:mod.py:1"
        route_sym = self._sym("GET /users", SymbolType.ROUTE, symbol_id=rid)
        handler_sym = self._sym("list_users", SymbolType.FUNCTION, symbol_id="sym:list_users")
        route_obj = self._route("users", "list_users", route_id=rid)
        pf = self._make_pf(routes=[route_obj], symbols=[route_sym, handler_sym])
        result = build([pf])
        hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
        assert len(hr_edges) >= 1

    def test_exact_route_logical_id(self):
        rid = "route:GET:/users/src/api/users.py:42"
        r = ParsedRoute(route_id=rid, route_path="/users/{user_id}",
                        method=HttpMethod.GET, handler_function="get_user",
                        start_line=42, confidence=Confidence.EXTRACTED)
        assert r.route_id == "route:GET:/users/src/api/users.py:42"
        parts = r.route_id.split(":")
        assert parts[0] == "route"
        assert parts[1] == "GET"

    def test_duplicate_evidence_edges_preserved(self):
        from fcode.graph.graph_builder import build
        imp1 = self._imp("os", line_number=1)
        imp2 = self._imp("os", line_number=5)
        pf = self._make_pf(imports=[imp1, imp2])
        result = build([pf])
        import_edges = [e for e in result.edges if e.relation == GraphRelation.IMPORTS]
        assert len(import_edges) == 2

    def test_graph_models_validate(self):
        node = GraphNodeInput(node_id="file:test.py", node_type=GraphNodeType.FILE,
                              label="test.py", source_file="test.py",
                              confidence=Confidence.EXTRACTED)
        assert node.node_id == "file:test.py"
        edge = GraphEdgeInput(source_node_id="a", target_node_id="b",
                              relation=GraphRelation.DEFINES,
                              confidence=Confidence.EXTRACTED)
        assert edge.relation == GraphRelation.DEFINES

    def test_no_variable_graph_nodes(self):
        from fcode.graph.graph_builder import build
        pf = self._make_pf(symbols=[
            self._sym("x", SymbolType.VARIABLE),
        ])
        result = build([pf])
        var_nodes = [n for n in result.nodes if n.node_type not in (GraphNodeType.FILE,)]
        assert len(var_nodes) == 0


class TestSecretSafety:
    def test_no_secret_in_serialized_models(self):
        sf = ScannedFile(file_path="secret.py", safe_content="[REDACTED]\n",
                         content_hash="abc", has_secrets=True)
        assert "sk_test" not in repr(sf)
        assert "sk_test" not in str(sf)

    def test_secret_absent_from_diagnostics(self):
        d = SkippedFileDiagnostic(file_path="secret.py", reason="file_skipped",
                                  details="Secret detected")
        assert "sk_test" not in d.details