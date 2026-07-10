"""Tests for python_ast.py (the main parser)."""

from fcode.parser.python_ast import parse
from fcode.contracts.enums import ParseStatus, SymbolType


def test_valid_module():
    content = "x = 1\n"
    result = parse("module.py", content)
    assert result.status == ParseStatus.PARSED
    assert result.file_path == "module.py"


def test_module_docstring():
    content = '"""Module doc."""\nimport os\n'
    result = parse("mod.py", content)
    assert result.status == ParseStatus.PARSED


def test_syntax_error():
    content = "def foo(:\n"
    result = parse("broken.py", content)
    assert result.status == ParseStatus.FAILED
    assert len(result.errors) == 1
    assert len(result.errors[0]) <= 500
    assert result.symbols == []
    assert result.imports == []
    assert result.routes == []


def test_functions():
    content = "def foo(): pass\ndef bar(): pass\n"
    result = parse("mod.py", content)
    funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
    assert len(funcs) == 2


def test_async_function():
    content = "async def fetch(): pass\n"
    result = parse("mod.py", content)
    funcs = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
    assert len(funcs) == 1


def test_classes():
    content = "class MyClass:\n    pass\n"
    result = parse("mod.py", content)
    classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
    assert len(classes) == 1


def test_methods():
    content = "class Foo:\n    def bar(self): pass\n"
    result = parse("mod.py", content)
    methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1


def test_async_method():
    content = "class Foo:\n    async def bar(self): pass\n"
    result = parse("mod.py", content)
    methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1


def test_nested_functions():
    content = "def outer():\n    def inner():\n        pass\n    pass\n"
    result = parse("mod.py", content)
    assert len(result.symbols) == 2
    names = {s.name for s in result.symbols}
    assert names == {"outer", "inner"}


def test_duplicate_symbols():
    content = "def foo(): pass\ndef foo(): pass\n"
    result = parse("mod.py", content)
    foos = [s for s in result.symbols if s.name == "foo"]
    assert len(foos) == 2


def test_imports():
    content = "import os\nfrom sys import path\n"
    result = parse("mod.py", content)
    assert len(result.imports) == 2


def test_routes():
    content = """
@app.get("/users")
def list_users():
    pass
"""
    result = parse("routes.py", content)
    assert len(result.routes) == 1
    assert result.routes[0].path == "/users"


def test_empty_file():
    result = parse("empty.py", "")
    assert result.status == ParseStatus.PARSED
    assert result.symbols == []


def test_indentation_error():
    content = "def foo():\n    pass\n  pass\n"
    result = parse("bad.py", content)
    assert result.status == ParseStatus.FAILED
    assert len(result.errors) == 1


def test_parser_uses_content_not_file():
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "secret.py")
        with open(fpath, "w") as f:
            f.write("import os\n")
        content = "x = 1\n"
        result = parse(fpath, content)
        assert result.status == ParseStatus.PARSED
        assert len(result.symbols) == 1
        assert result.symbols[0].name == "x"
