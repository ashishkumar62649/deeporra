"""Python AST parser — parse Python source into symbols, imports, and routes."""

import ast

from fcode.contracts.enums import ParseStatus
from fcode.contracts.models import ParsedFile
from fcode.parser.symbol_extractor import extract_symbols
from fcode.parser.import_extractor import extract_imports
from fcode.parser.route_detector import detect_routes


MAX_ERROR_LENGTH = 500


def parse(file_path: str, content: str) -> ParsedFile:
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        msg = str(e)
        if len(msg) > MAX_ERROR_LENGTH:
            msg = msg[:MAX_ERROR_LENGTH]
        return ParsedFile(
            file_path=file_path,
            status=ParseStatus.FAILED,
            symbols=[],
            imports=[],
            routes=[],
            errors=[msg],
        )

    symbols = extract_symbols(tree, file_path)
    imports = extract_imports(tree)
    routes = detect_routes(tree, file_path)

    return ParsedFile(
        file_path=file_path,
        status=ParseStatus.PARSED,
        symbols=symbols,
        imports=imports,
        routes=routes,
        errors=[],
    )
