"""Symbol extraction — extract functions, classes, methods, and variables from AST."""

import ast
from typing import Generator

from fcode.contracts import Confidence, ParsedSymbol, SymbolType


def extract_symbols(tree: ast.AST, file_path: str) -> Generator[ParsedSymbol, None, None]:
    yield from _visit(tree, [])


def _extract_bases(node: ast.ClassDef) -> list[str]:
    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
    return bases


def _extract_calls(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                name = child.func.id
                if name not in calls:
                    calls.append(name)
            elif isinstance(child.func, ast.Attribute):
                if isinstance(child.func.value, ast.Name):
                    name = f"{child.func.value.id}.{child.func.attr}"
                    if name not in calls:
                        calls.append(name)
    return calls


def _visit(node: ast.AST, class_stack: list[str]) -> Generator[ParsedSymbol, None, None]:
    if isinstance(node, ast.ClassDef):
        end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
        parent = class_stack[-1] if class_stack else None
        qualified = ".".join(class_stack + [node.name]) if class_stack else node.name
        bases = _extract_bases(node)
        metadata = {"bases": bases} if bases else None
        yield ParsedSymbol(
            symbol_type=SymbolType.CLASS,
            name=node.name,
            qualified_name=qualified,
            start_line=node.lineno,
            end_line=end_lineno,
            parent=parent,
            docstring=ast.get_docstring(node),
            confidence=Confidence.EXTRACTED,
            metadata=metadata,
        )
        class_stack.append(node.name)
        for child in ast.iter_child_nodes(node):
            yield from _visit(child, class_stack)
        class_stack.pop()

    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
        is_method = bool(class_stack)
        st = SymbolType.METHOD if is_method else SymbolType.FUNCTION
        parent = class_stack[-1] if class_stack else None
        qualified = ".".join(class_stack + [node.name]) if class_stack else node.name
        sig = _format_signature(node)
        calls = _extract_calls(node)
        metadata = {"calls": calls} if calls else None
        yield ParsedSymbol(
            symbol_type=st,
            name=node.name,
            qualified_name=qualified,
            start_line=node.lineno,
            end_line=end_lineno,
            parent=parent,
            docstring=ast.get_docstring(node),
            signature=sig,
            confidence=Confidence.EXTRACTED,
            metadata=metadata,
        )
        for child in ast.iter_child_nodes(node):
            yield from _visit(child, class_stack)

    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and not class_stack:
                end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
                yield ParsedSymbol(
                    symbol_type=SymbolType.VARIABLE,
                    name=target.id,
                    qualified_name=target.id,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    confidence=Confidence.INFERRED,
                )

    else:
        for child in ast.iter_child_nodes(node):
            yield from _visit(child, class_stack)


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
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
