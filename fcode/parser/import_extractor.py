"""Import extraction — extract import statements from AST."""

import ast
from typing import Generator

from fcode.contracts import Confidence, ParsedImport


def extract_imports(tree: ast.AST, file_path: str) -> Generator[ParsedImport, None, None]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ParsedImport(
                    module_name=alias.name,
                    imported_names=[alias.asname or alias.name],
                    alias=alias.asname,
                    line_number=node.lineno,
                    confidence=Confidence.EXTRACTED,
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.asname or alias.name for alias in node.names]
            for alias in node.names:
                yield ParsedImport(
                    module_name=module,
                    imported_names=[alias.asname or alias.name],
                    alias=alias.asname,
                    line_number=node.lineno,
                    is_relative=(node.level or 0) > 0,
                    confidence=Confidence.EXTRACTED,
                )
