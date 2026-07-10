"""Tests for route_detector.py."""

import ast
from fcode.parser.route_detector import extract_routes
from fcode.contracts import HttpMethod


def _routes(code):
    return list(extract_routes(ast.parse(code), "routes.py"))


def test_get_route():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    route, sym = results[0]
    assert route.method == HttpMethod.GET
    assert route.route_path == "/users"
    assert route.handler_function == "list_users"


def test_post_route():
    code = """
@app.post("/users")
def create_user():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    route, sym = results[0]
    assert route.method == HttpMethod.POST


def test_put_route():
    code = """
@app.put("/users/{id}")
def update_user():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    route, sym = results[0]
    assert route.method == HttpMethod.PUT


def test_delete_route():
    code = """
@app.delete("/users/{id}")
def delete_user():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    route, sym = results[0]
    assert route.method == HttpMethod.DELETE


def test_patch_route():
    code = """
@app.patch("/users/{id}")
def patch_user():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    route, sym = results[0]
    assert route.method == HttpMethod.PATCH


def test_all_five_methods():
    code = """
@app.get("/a")
def a(): pass
@app.post("/b")
def b(): pass
@app.put("/c")
def c(): pass
@app.delete("/d")
def d(): pass
@app.patch("/e")
def e(): pass
"""
    results = _routes(code)
    assert len(results) == 5
    methods = {r[0].method for r in results}
    assert methods == {HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.DELETE, HttpMethod.PATCH}


def test_route_id_format():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    results = _routes(code)
    route, sym = results[0]
    assert "route:GET:" in route.route_id
    assert route.route_id.endswith(":routes.py:3")


def test_start_line_is_decorator_line():
    code = """
@app.get("/items")
def list_items():
    pass
"""
    results = _routes(code)
    route, sym = results[0]
    assert route.start_line == 2


def test_multiple_routes():
    code = """
@app.get("/a")
def a(): pass

@app.post("/b")
def b(): pass
"""
    results = _routes(code)
    assert len(results) == 2
    assert results[0][0].route_path == "/a"
    assert results[1][0].route_path == "/b"


def test_router_decorator():
    code = """
@router.get("/items")
def list_items():
    pass
"""
    results = _routes(code)
    assert len(results) == 1
    assert results[0][0].handler_function == "list_items"


def test_dynamic_expression_skipped():
    code = """
@app.get(path_var)
def handler():
    pass
"""
    results = _routes(code)
    assert len(results) == 0


def test_shared_uuid():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    results = _routes(code)
    route, sym = results[0]
    assert sym.symbol_id == route.route_id


def test_route_symbol_type():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    results = _routes(code)
    route, sym = results[0]
    from fcode.contracts import SymbolType
    assert sym.symbol_type == SymbolType.ROUTE


def test_route_symbol_name():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    results = _routes(code)
    route, sym = results[0]
    assert sym.name == "GET /users"
