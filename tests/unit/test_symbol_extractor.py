"""Tests for symbol_extractor.py."""

import ast
from fcode.parser.symbol_extractor import extract_symbols
from fcode.contracts.enums import SymbolType


def test_function():
    code = "def hello():\n    pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert len(syms) == 1
    assert syms[0].name == "hello"
    assert syms[0].symbol_type == SymbolType.FUNCTION


def test_async_function():
    code = "async def fetch():\n    pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert len(syms) == 1
    assert syms[0].symbol_type == SymbolType.FUNCTION


def test_class():
    code = "class MyClass:\n    pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert len(syms) == 1
    assert syms[0].name == "MyClass"
    assert syms[0].symbol_type == SymbolType.CLASS


def test_method():
    code = "class Foo:\n    def bar(self):\n        pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert len(syms) == 2
    methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "bar"
    assert methods[0].parent == "Foo"


def test_async_method():
    code = "class Foo:\n    async def bar(self):\n        pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "bar"


def test_nested_function():
    code = "def outer():\n    def inner():\n        pass\n    pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert len(syms) == 2
    names = {s.name for s in syms}
    assert names == {"outer", "inner"}


def test_duplicate_names():
    code = "def foo(): pass\ndef foo(x): pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    foos = [s for s in syms if s.name == "foo"]
    assert len(foos) == 2


def test_variable():
    code = "x = 42\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    vars_ = [s for s in syms if s.symbol_type == SymbolType.VARIABLE]
    assert len(vars_) == 1
    assert vars_[0].name == "x"


def test_line_ranges():
    code = "def foo():\n    pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert syms[0].start_line == 1
    assert syms[0].end_line >= 2


def test_docstring():
    code = 'def foo():\n    """Do stuff."""\n    pass\n'
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    assert syms[0].docstring == "Do stuff."


def test_empty_module():
    tree = ast.parse("")
    syms = extract_symbols(tree, "module.py")
    assert syms == []


def test_deterministic_ordering():
    code = "def b(): pass\ndef a(): pass\n"
    tree = ast.parse(code)
    syms = extract_symbols(tree, "module.py")
    names = [s.name for s in syms]
    assert names == ["b", "a"]
