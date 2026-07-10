"""Symbol extraction — extract functions, classes, methods, and variables from AST."""

import ast
from typing import Optional

from fcode.contracts.enums import SymbolType
from fcode.contracts.models import ParsedSymbol


def _module_from_path(file_path: str) -> str:
    return file_path.replace("/", ".").replace("\\", ".").replace(".py", "").replace(".pyw", "")


def _build_signature(node: ast.AST) -> Optional[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        parts = ["def ", node.name, "("]
        arg_strings = []
        for arg in args.args:
            arg_strings.append(arg.arg)
        if args.vararg:
            arg_strings.append(f"*{args.vararg.arg}")
        for arg in args.kwonlyargs:
            arg_strings.append(arg.arg)
        if args.kwarg:
            arg_strings.append(f"**{args.kwarg.arg}")
        parts.append(", ".join(arg_strings))
        parts.append(")")
        return "".join(parts)
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases]
        if bases:
            return f"class {node.name}({', '.join(bases)})"
        return f"class {node.name}"
    return None


def _get_docstring(node: ast.AST) -> Optional[str]:
    try:
        return ast.get_docstring(node)
    except Exception:
        return None


def extract_symbols(tree: ast.AST, file_path: str) -> list[ParsedSymbol]:
    module_name = _module_from_path(file_path)
    symbols: list[ParsedSymbol] = []
    _visit(tree, module_name, symbols, None)
    symbols.sort(key=lambda s: (s.start_line, s.end_line, s.name))
    return symbols


def _visit(
    node: ast.AST,
    module_name: str,
    symbols: list[ParsedSymbol],
    parent: Optional[str],
):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef):
            _add_function(child, module_name, symbols, parent)
            _visit(child, module_name, symbols, child.name)
        elif isinstance(child, ast.AsyncFunctionDef):
            _add_function(child, module_name, symbols, parent)
            _visit(child, module_name, symbols, child.name)
        elif isinstance(child, ast.ClassDef):
            sym = ParsedSymbol(
                name=child.name,
                symbol_type=SymbolType.CLASS,
                start_line=child.lineno,
                end_line=child.end_lineno or child.lineno,
                parent=parent,
                docstring=_get_docstring(child),
            )
            symbols.append(sym)
            _visit(child, module_name, symbols, child.name)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    sym = ParsedSymbol(
                        name=target.id,
                        symbol_type=SymbolType.VARIABLE,
                        start_line=child.lineno,
                        end_line=child.end_lineno or child.lineno,
                        parent=parent,
                    )
                    symbols.append(sym)


def _add_function(
    node: ast.AST,
    module_name: str,
    symbols: list[ParsedSymbol],
    parent: Optional[str],
):
    name = node.name
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if parent is None:
            sym_type = SymbolType.FUNCTION
        else:
            sym_type = SymbolType.METHOD
        sym = ParsedSymbol(
            name=name,
            symbol_type=sym_type,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            parent=parent,
            docstring=_get_docstring(node),
        )
        symbols.append(sym)
