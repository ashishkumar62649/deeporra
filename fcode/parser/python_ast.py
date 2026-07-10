"""Python AST — parse a Python source file into its AST."""

import ast

from fcode.contracts import (
    Confidence,
    ParseStatus,
    ParsedFile,
    ParsedRoute,
    ParsedSymbol,
    ScannedFile,
    SymbolType,
)
from fcode.parser.import_extractor import extract_imports
from fcode.parser.route_detector import extract_routes
from fcode.parser.symbol_extractor import extract_symbols


def parse(file: ScannedFile) -> ParsedFile:
    return parse_python_file(file)


def parse_python_file(file: ScannedFile) -> ParsedFile:
    if file.is_binary or not file.safe_content.strip():
        return ParsedFile(
            file_path=file.file_path,
            file_type=file.file_type,
            status=ParseStatus.NOT_APPLICABLE,
            file_id=file.file_id,
            line_count=file.line_count,
        )

    try:
        tree = ast.parse(file.safe_content, filename=file.file_path)
    except SyntaxError as exc:
        msg = str(exc.msg)[:500]
        return ParsedFile(
            file_path=file.file_path,
            file_type=file.file_type,
            status=ParseStatus.ERROR,
            errors=[msg],
            file_id=file.file_id,
            line_count=file.line_count,
        )

    symbols: list[ParsedSymbol] = list(extract_symbols(tree, file.file_path))
    imports = list(extract_imports(tree, file.file_path))
    routes: list[ParsedRoute] = []
    route_symbols: list[ParsedSymbol] = []

    result_routes = list(extract_routes(tree, file.file_path))
    for route, route_sym in result_routes:
        routes.append(route)
        route_sym.symbol_id = route.route_id
        route_symbols.append(route_sym)

    symbols.extend(route_symbols)

    for sym in symbols:
        if not sym.symbol_id:
            sym.symbol_id = f"{sym.symbol_type.value}:{file.file_path}:{sym.name}:{sym.start_line}"
        if not sym.file_id:
            sym.file_id = file.file_id

    for imp in imports:
        if not imp.file_id:
            imp.file_id = file.file_id

    for route in routes:
        if not route.file_id:
            route.file_id = file.file_id

    return ParsedFile(
        file_path=file.file_path,
        file_type=file.file_type,
        status=ParseStatus.PARSED,
        symbols=symbols,
        imports=imports,
        routes=routes,
        file_id=file.file_id,
        line_count=file.line_count,
    )
