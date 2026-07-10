"""Route detection — FastAPI-style route detection from decorators."""

import ast

from fcode.contracts.enums import HttpMethod
from fcode.contracts.models import ParsedRoute


DECORATOR_METHODS = {
    "get": HttpMethod.GET,
    "post": HttpMethod.POST,
    "put": HttpMethod.PUT,
    "delete": HttpMethod.DELETE,
    "patch": HttpMethod.PATCH,
}


def detect_routes(tree: ast.AST, file_path: str) -> list[ParsedRoute]:
    routes: list[ParsedRoute] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            route = _parse_decorator(decorator, node)
            if route is not None:
                routes.append(route)
    routes.sort(key=lambda r: r.start_line)
    return routes


def _parse_decorator(decorator: ast.expr, handler: ast.AST) -> ParsedRoute | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name):
        return None
    decorator_obj = func.value.id
    if decorator_obj not in ("app", "router"):
        return None
    method_name = func.attr
    http_method = DECORATOR_METHODS.get(method_name)
    if http_method is None:
        return None
    if not decorator.args:
        return None
    path_arg = decorator.args[0]
    if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
        return None
    route_path = path_arg.value
    route = ParsedRoute(
        method=http_method,
        path=route_path,
        handler=handler.name,
        start_line=decorator.lineno,
    )
    return route
