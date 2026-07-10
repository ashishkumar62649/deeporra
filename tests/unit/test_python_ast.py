"""Tests for python_ast.py (the main parser)."""

from fcode.contracts import FileType, ParseStatus, ScannedFile, SymbolType
from fcode.parser.python_ast import parse_python_file, parse


def _file(path, content="", is_binary=False) -> ScannedFile:
    return ScannedFile(
        file_path=path,
        file_type=FileType.SOURCE if not path.startswith("test_") else FileType.TEST,
        size_bytes=len(content.encode("utf-8")),
        is_binary=is_binary,
        safe_content=content,
        content_hash="",
        file_id=f"file:{path}",
    )


def test_parse_protocol_method():
    """The public parse() method must exist and accept ScannedFile."""
    f = _file("mod.py", "x = 1\n")
    result = parse(f)
    assert result.status == ParseStatus.PARSED


def test_valid_module():
    f = _file("module.py", "x = 1\n")
    result = parse_python_file(f)
    assert result.status == ParseStatus.PARSED
    assert result.file_path == "module.py"


def test_syntax_error():
    f = _file("broken.py", "def foo(:\n")
    result = parse_python_file(f)
    assert result.status == ParseStatus.ERROR
    assert len(result.errors) >= 1


def test_functions():
    f = _file("mod.py", "def foo(): pass\ndef bar(): pass\n")
    result = parse_python_file(f)
    funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
    assert len(funcs) == 2


def test_async_function():
    f = _file("mod.py", "async def fetch(): pass\n")
    result = parse_python_file(f)
    funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
    assert len(funcs) == 1


def test_classes():
    f = _file("mod.py", "class MyClass:\n    pass\n")
    result = parse_python_file(f)
    classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
    assert len(classes) == 1


def test_methods():
    f = _file("mod.py", "class Foo:\n    def bar(self): pass\n")
    result = parse_python_file(f)
    methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "bar"


def test_variables():
    f = _file("mod.py", "x = 42\n")
    result = parse_python_file(f)
    vars_ = [s for s in result.symbols if s.symbol_type == SymbolType.VARIABLE]
    assert len(vars_) == 1
    assert vars_[0].name == "x"


def test_imports():
    f = _file("mod.py", "import os\nfrom sys import path\n")
    result = parse_python_file(f)
    assert len(result.imports) == 2


def test_routes():
    f = _file("routes.py", """
@app.get("/users")
def list_users():
    pass
""")
    result = parse_python_file(f)
    assert len(result.routes) == 1
    assert result.routes[0].route_path == "/users"


def test_route_symbol_included():
    f = _file("routes.py", """
@app.get("/users")
def list_users():
    pass
""")
    result = parse_python_file(f)
    route_syms = [s for s in result.symbols if s.symbol_type == SymbolType.ROUTE]
    assert len(route_syms) == 1
    assert route_syms[0].symbol_id == result.routes[0].route_id


def test_empty_file():
    f = _file("empty.py", "")
    result = parse_python_file(f)
    assert result.status == ParseStatus.NOT_APPLICABLE
    assert len(result.symbols) == 0


def test_binary_file_skipped():
    f = _file("data.bin", "", is_binary=True)
    result = parse_python_file(f)
    assert result.status == ParseStatus.NOT_APPLICABLE


def test_nested_functions():
    f = _file("mod.py", "def outer():\n    def inner():\n        pass\n    pass\n")
    result = parse_python_file(f)
    assert len(result.symbols) == 2
    names = {s.name for s in result.symbols}
    assert names == {"outer", "inner"}


def test_parser_preserves_file_id():
    f = _file("mod.py", "x = 1\n")
    result = parse_python_file(f)
    assert result.file_id == "file:mod.py"


def test_parser_never_opens_file(monkeypatch):
    import builtins
    original_open = builtins.open
    calls = []

    def no_open(*args, **kwargs):
        calls.append(args)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", no_open)
    f = _file("nonexistent.py", "x = 1\n")
    result = parse_python_file(f)
    assert result.status == ParseStatus.PARSED
    file_calls = [c for c in calls if "nonexistent" in str(c)]
    assert len(file_calls) == 0


def test_syntax_error_sanitized():
    f = _file("bad.py", "def foo(:\n")
    result = parse_python_file(f)
    assert result.status == ParseStatus.ERROR
    assert all(len(e) <= 500 for e in result.errors)
    assert result.symbols == []
    assert result.imports == []
    assert result.routes == []
