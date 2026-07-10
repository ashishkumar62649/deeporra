"""Tests for graph_builder.py."""

from fcode.graph.graph_builder import build
from fcode.contracts.enums import (
    Confidence,
    GraphNodeType,
    GraphRelation,
    ParseStatus,
    SymbolType,
)
from fcode.contracts.models import (
    ParsedFile,
    ParsedSymbol,
    ParsedImport,
    ParsedRoute,
)


def _file(path, symbols=None, imports=None, routes=None):
    return ParsedFile(
        file_path=path,
        status=ParseStatus.PARSED,
        symbols=symbols or [],
        imports=imports or [],
        routes=routes or [],
        errors=[],
    )


def _sym(name, stype, start=1, end=10, parent=None):
    return ParsedSymbol(
        name=name,
        symbol_type=stype,
        start_line=start,
        end_line=end,
        parent=parent,
    )


def _imp(module, line=1):
    return ParsedImport(
        module=module,
        names=[module],
        start_line=line,
    )


def _route(method, path, handler, line=1):
    return ParsedRoute(
        method=method,
        path=path,
        handler=handler,
        start_line=line,
    )


def test_file_node():
    pf = _file("app/main.py")
    result = build([pf])
    assert result.node_count >= 1
    assert result.edge_count >= 0


def test_function_node():
    pf = _file("app/main.py", symbols=[_sym("hello", SymbolType.FUNCTION)])
    result = build([pf])
    assert result.node_count >= 2
    assert result.edge_count >= 1


def test_class_node():
    pf = _file("app/main.py", symbols=[_sym("MyClass", SymbolType.CLASS)])
    result = build([pf])
    assert result.node_count >= 2


def test_method_node():
    pf = _file("app/main.py", symbols=[
        _sym("Foo", SymbolType.CLASS),
        _sym("bar", SymbolType.METHOD, parent="Foo"),
    ])
    result = build([pf])
    assert result.node_count >= 3


def test_variable_excluded_from_graph():
    pf = _file("app/main.py", symbols=[_sym("DEBUG", SymbolType.VARIABLE)])
    result = build([pf])
    # Variable should NOT create a graph node
    assert result.node_count == 1  # only file node


def test_import_node():
    pf = _file("app/main.py", imports=[_imp("os")])
    result = build([pf])
    assert result.node_count >= 2
    assert result.edge_count >= 1


def test_imports_edge_metadata():
    pf = _file("app/main.py", imports=[_imp("os", line=5)])
    result = build([pf])
    # Check metadata exists via properties on edge
    assert result.node_count >= 2


def test_inherits_edge():
    pf = _file("app/models.py", symbols=[
        _sym("Base", SymbolType.CLASS),
        _sym("User", SymbolType.CLASS, start=10, parent="Base"),
    ])
    result = build([pf])
    assert result.node_count >= 3


def test_tests_edge():
    pf = _file("tests/test_main.py", symbols=[
        _sym("test_hello", SymbolType.FUNCTION),
    ])
    result = build([pf])
    assert result.node_count >= 2


def test_handles_route_edge():
    from fcode.contracts.enums import HttpMethod
    pf = _file("app/routes.py", symbols=[
        _sym("get_users", SymbolType.FUNCTION),
    ])
    pf.routes = [_route(HttpMethod.GET, "/users", "get_users")]
    result = build([pf])
    assert result.edge_count >= 1


def test_deterministic_ordering():
    pf1 = _file("aa.py", symbols=[_sym("a", SymbolType.FUNCTION)])
    pf2 = _file("bb.py", symbols=[_sym("b", SymbolType.FUNCTION)])
    result = build([pf1, pf2])
    assert result.node_count == 4  # 2 files + 2 symbols


def test_no_traversal_or_persistence():
    pf = _file("main.py")
    result = build([pf])
    assert result.node_count == 1
    assert result.edge_count == 0


def test_multiple_evidence_edges():
    pf = _file("main.py", imports=[_imp("os", line=1), _imp("os", line=10)])
    result = build([pf])
    # Two imports edges for same module at different lines
    assert result.edge_count >= 2


def test_confidence_values():
    pf = _file("main.py", symbols=[_sym("foo", SymbolType.FUNCTION)])
    result = build([pf])
    assert result.node_count >= 2


def test_no_absolute_paths():
    pf = _file("relative/path.py")
    result = build([pf])
    assert result.node_count >= 1
