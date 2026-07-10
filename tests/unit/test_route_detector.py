"""Tests for route_detector.py."""

import ast
from fcode.parser.route_detector import detect_routes
from fcode.contracts.enums import HttpMethod


def _routes(code):
    return detect_routes(ast.parse(code), "routes.py")


def test_get_route():
    code = """
@app.get("/users")
def list_users():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].method == HttpMethod.GET
    assert routes[0].path == "/users"
    assert routes[0].handler == "list_users"


def test_post_route():
    code = """
@app.post("/users")
def create_user():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].method == HttpMethod.POST


def test_put_route():
    code = """
@app.put("/users/{id}")
def update_user():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].method == HttpMethod.PUT


def test_delete_route():
    code = """
@app.delete("/users/{id}")
def delete_user():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].method == HttpMethod.DELETE


def test_patch_route():
    code = """
@app.patch("/users/{id}")
def patch_user():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].method == HttpMethod.PATCH


def test_router_decorator():
    code = """
@router.get("/items")
def list_items():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 1
    assert routes[0].handler == "list_items"


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
    routes = _routes(code)
    assert len(routes) == 5
    methods = {r.method for r in routes}
    assert methods == {HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.DELETE, HttpMethod.PATCH}


def test_unsupported_dynamic_expression():
    code = """
@app.get(path_var)
def handler():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 0


def test_not_app_or_router():
    code = """
@other.get("/x")
def handler():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 0


def test_no_flask_detection():
    code = """
@app.route("/users")
def users():
    pass
"""
    routes = _routes(code)
    assert len(routes) == 0


def test_decorator_line():
    code = """
@app.get("/items")
def list_items():
    pass
"""
    routes = _routes(code)
    assert routes[0].start_line == 2


def test_multiple_routes():
    code = """
@app.get("/a")
def a(): pass

@app.post("/b")
def b(): pass
"""
    routes = _routes(code)
    assert len(routes) == 2
    assert routes[0].path == "/a"
    assert routes[1].path == "/b"
