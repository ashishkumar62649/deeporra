"""Import extraction — extract import statements from AST."""

import ast

from fcode.contracts.models import ParsedImport


def extract_imports(tree: ast.AST) -> list[ParsedImport]:
    imports: list[ParsedImport] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imp = ParsedImport(
                    module=alias.name,
                    names=[alias.asname or alias.name],
                    start_line=node.lineno,
                    is_relative=False,
                )
                imports.append(imp)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            is_relative = node.level is not None and node.level > 0
            if is_relative:
                prefix = "." * node.level
                module = f"{prefix}{module}" if module else prefix
            for alias in node.names:
                imp = ParsedImport(
                    module=module,
                    names=[alias.asname or alias.name],
                    start_line=node.lineno,
                    is_relative=is_relative,
                )
                imports.append(imp)
    imports.sort(key=lambda i: i.start_line)
    return imports
