"""Route detection — detect FastAPI route decorators in AST."""

import ast
from typing import Generator

from fcode.contracts import Confidence, HttpMethod, ParsedRoute, ParsedSymbol, SymbolType

FASTAPI_ATTRIBUTES = {"get", "post", "put", "delete", "patch"}


def extract_routes(tree: ast.AST, file_path: str) -> Generator[tuple[ParsedRoute, ParsedSymbol], None, None]:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            result = _parse_decorator(deco)
            if result:
                method, route_path = result
                deco_line = getattr(deco, "lineno", node.lineno)
                end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
                route_id = f"route:{method.value}:{route_path}:{file_path}:{deco_line}"

                route = ParsedRoute(
                    route_id=route_id,
                    route_path=route_path,
                    method=method,
                    handler_function=node.name,
                    start_line=deco_line,
                    docstring=ast.get_docstring(node),
                    decorators=[ast.unparse(deco) if hasattr(ast, 'unparse') else ""],
                    confidence=Confidence.EXTRACTED,
                )

                sig = _format_handler_signature(node)
                qualified = _compute_qualified_name(node)
                route_symbol = ParsedSymbol(
                    symbol_type=SymbolType.ROUTE,
                    name=f"{method.value} {route_path}",
                    qualified_name=qualified,
                    start_line=deco_line,
                    end_line=end_lineno,
                    docstring=ast.get_docstring(node),
                    signature=sig,
                    symbol_id=route_id,
                    confidence=Confidence.EXTRACTED,
                )

                yield route, route_symbol


def _parse_decorator(deco: ast.expr) -> tuple[HttpMethod, str] | None:
    if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
        if deco.func.attr in FASTAPI_ATTRIBUTES:
            if isinstance(deco.func.value, ast.Name) and deco.func.value.id in ("app", "router"):
                path = _extract_static_path(deco)
                if path is not None:
                    return HttpMethod(deco.func.attr.upper()), path
    return None


def _extract_static_path(deco: ast.Call) -> str | None:
    if deco.args and isinstance(deco.args[0], ast.Constant) and isinstance(deco.args[0].value, str):
        return deco.args[0].value
    return None


def _format_handler_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    parts = ["("]
    all_args = [a.arg for a in args.args]
    if args.vararg:
        all_args.append(f"*{args.vararg.arg}")
    all_args.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg:
        all_args.append(f"**{args.kwarg.arg}")
    parts.append(", ".join(all_args))
    parts.append(")")
    returns = ""
    if node.returns:
        try:
            returns = ast.unparse(node.returns)
        except Exception:
            returns = ""
    if returns:
        parts.append(f" -> {returns}")
    return "".join(parts)


def _compute_qualified_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return node.name
