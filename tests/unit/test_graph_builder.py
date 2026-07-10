"""Tests for graph_builder.py."""

from fcode.contracts import (
    Confidence, FileType, GraphBuildResult, GraphNodeInput, GraphNodeType,
    GraphRelation, HttpMethod, ParsedFile, ParsedImport, ParsedRoute,
    ParsedSymbol, ParseStatus, SymbolType,
)
from fcode.graph.graph_builder import build, _infer_tested_name


def _pf(path: str) -> ParsedFile:
    return ParsedFile(
        file_path=path,
        file_id=f"file:{path}",
        file_type=FileType.SOURCE,
        status=ParseStatus.PARSED,
    )


def _sym(name: str, typ: SymbolType, **kw) -> ParsedSymbol:
    kw.setdefault("symbol_id", f"sym:{name}")
    kw.setdefault("start_line", 1)
    kw.setdefault("end_line", 1)
    return ParsedSymbol(name=name, symbol_type=typ, confidence=Confidence.EXTRACTED, **kw)


def _imp(module: str, names: list[str] | None = None, **kw) -> ParsedImport:
    kw.setdefault("line_number", 1)
    return ParsedImport(
        module_name=module,
        imported_names=names or [module],
        confidence=Confidence.EXTRACTED,
        **kw,
    )


def _route(path: str, fn: str, **kw) -> ParsedRoute:
    kw.setdefault("route_id", f"route:{path}")
    kw.setdefault("start_line", 1)
    return ParsedRoute(
        route_path=f"/{path}",
        handler_function=fn,
        method=HttpMethod.GET,
        confidence=Confidence.EXTRACTED,
        **kw,
    )


def test_build_returns_graphbuildresult():
    result = build([])
    assert isinstance(result, GraphBuildResult)


def test_empty_build():
    result = build([])
    assert result.node_count == 0
    assert result.edge_count == 0


def test_function_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 1
    assert fn_nodes[0].label == "foo"
    assert fn_nodes[0].source_file == "mod.py"


def test_class_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("MyClass", SymbolType.CLASS))
    result = build([pf])
    cls_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.CLASS]
    assert len(cls_nodes) == 1
    assert cls_nodes[0].label == "MyClass"


def test_method_node():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("bar", SymbolType.METHOD))
    result = build([pf])
    m_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.METHOD]
    assert len(m_nodes) == 1
    assert m_nodes[0].label == "bar"


def test_route_node():
    rid = "route:GET:/users"
    pf = _pf("routes.py")
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.symbols.append(_sym("GET /users", SymbolType.ROUTE, symbol_id=rid))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION))
    result = build([pf])
    r_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.ROUTE]
    assert len(r_nodes) >= 1


def test_handles_route_edge():
    rid = "route:GET:/users"
    pf = _pf("routes.py")
    pf.routes.append(_route("users", "list_users", route_id=rid))
    pf.symbols.append(_sym("GET /users", SymbolType.ROUTE, symbol_id=rid))
    pf.symbols.append(_sym("list_users", SymbolType.FUNCTION))
    result = build([pf])
    edges = [e for e in result.edges if e.relation == GraphRelation.DEFINES]
    assert len(edges) >= 1


def test_file_node():
    pf = _pf("mod.py")
    result = build([pf])
    file_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FILE]
    assert len(file_nodes) == 1
    assert file_nodes[0].label == "mod.py"


def test_test_symbol_ignored():
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.append(_sym("test_foo", SymbolType.FUNCTION))
    result = build([pf])
    assert len(result.nodes) >= 1


def test_multiple_files():
    pf1 = _pf("mod1.py")
    pf1.symbols.append(_sym("foo", SymbolType.FUNCTION))
    pf2 = _pf("mod2.py")
    pf2.symbols.append(_sym("bar", SymbolType.FUNCTION))
    result = build([pf1, pf2])
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 2


def test_edge_count_greater_than_zero_with_symbols():
    pf = _pf("mod.py")
    pf.symbols.append(_sym("foo", SymbolType.FUNCTION))
    result = build([pf])
    assert result.edge_count > 0


def test_inherits_edge():
    base = _sym("Base", SymbolType.CLASS, symbol_id="sym:Base")
    child = _sym("Child", SymbolType.CLASS, symbol_id="sym:Child",
                  metadata={"bases": ["Base"]})
    pf = _pf("mod.py")
    pf.symbols.extend([base, child])
    result = build([pf])
    inherits_edges = [e for e in result.edges if e.relation == GraphRelation.INHERITS]
    assert len(inherits_edges) >= 1
    assert inherits_edges[0].source_node_id == "sym:Child"
    assert inherits_edges[0].target_node_id == "sym:Base"


def test_calls_edge():
    caller = _sym("caller", SymbolType.FUNCTION, symbol_id="sym:caller",
                   metadata={"calls": ["callee"]})
    callee = _sym("callee", SymbolType.FUNCTION, symbol_id="sym:callee")
    pf = _pf("mod.py")
    pf.symbols.extend([caller, callee])
    result = build([pf])
    calls_edges = [e for e in result.edges if e.relation == GraphRelation.CALLS]
    assert len(calls_edges) >= 1
    assert calls_edges[0].source_node_id == "sym:caller"
    assert calls_edges[0].target_node_id == "sym:callee"


def test_tests_edge():
    test_fn = _sym("test_foo", SymbolType.FUNCTION, symbol_id="sym:test_foo")
    target_fn = _sym("foo", SymbolType.FUNCTION, symbol_id="sym:foo")
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.extend([test_fn, target_fn])
    result = build([pf])
    tests_edges = [e for e in result.edges if e.relation == GraphRelation.TESTS]
    assert len(tests_edges) >= 1
    assert tests_edges[0].source_node_id == "sym:test_foo"


def test_unresolved_tests_no_edge():
    test_fn = _sym("test_unknown", SymbolType.FUNCTION, symbol_id="sym:test_unknown")
    pf = _pf("test_mod.py")
    pf.file_type = FileType.TEST
    pf.symbols.append(test_fn)
    result = build([pf])
    tests_edges = [e for e in result.edges if e.relation == GraphRelation.TESTS]
    assert len(tests_edges) == 0


def test_normal_function_not_test():
    fn = _sym("helper", SymbolType.FUNCTION, symbol_id="sym:helper")
    pf = _pf("mod.py")
    pf.symbols.append(fn)
    result = build([pf])
    test_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.TEST]
    assert len(test_nodes) == 0
    fn_nodes = [n for n in result.nodes if n.node_type == GraphNodeType.FUNCTION]
    assert len(fn_nodes) == 1


def test_handles_route_edge():
    rid = "route:GET:/users:routes.py:1"
    route_sym = _sym("GET /users", SymbolType.ROUTE, symbol_id=rid)
    handler_sym = _sym("list_users", SymbolType.FUNCTION, symbol_id="sym:list_users")
    route = _route("users", "list_users", route_id=rid)
    pf = _pf("routes.py")
    pf.routes.append(route)
    pf.symbols.extend([route_sym, handler_sym])
    result = build([pf])
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) >= 1
    assert hr_edges[0].source_node_id == rid
    assert hr_edges[0].target_node_id == "sym:list_users"


def test_handles_route_confidence():
    rid = "route:GET:/items:routes.py:5"
    route_sym = _sym("GET /items", SymbolType.ROUTE, symbol_id=rid)
    handler_sym = _sym("get_items", SymbolType.FUNCTION, symbol_id="sym:get_items")
    route = _route("items", "get_items", route_id=rid, start_line=5)
    pf = _pf("routes.py")
    pf.routes.append(route)
    pf.symbols.extend([route_sym, handler_sym])
    result = build([pf])
    hr_edges = [e for e in result.edges if e.relation == GraphRelation.HANDLES_ROUTE]
    assert len(hr_edges) >= 1
    assert hr_edges[0].confidence == Confidence.EXTRACTED


def test_duplicate_import_edges_preserved():
    imp1 = _imp("os", line_number=1)
    imp2 = _imp("os", line_number=5)
    pf = _pf("mod.py")
    pf.imports.extend([imp1, imp2])
    result = build([pf])
    import_edges = [e for e in result.edges if e.relation == GraphRelation.IMPORTS]
    assert len(import_edges) == 2


def test_variable_no_graph_node():
    var = _sym("x", SymbolType.VARIABLE)
    pf = _pf("mod.py")
    pf.symbols.append(var)
    result = build([pf])
    non_file_nodes = [n for n in result.nodes if n.node_type != GraphNodeType.FILE]
    assert len(non_file_nodes) == 0
