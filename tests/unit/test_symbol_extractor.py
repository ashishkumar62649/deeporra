"""Tests for symbol_extractor.py."""

import ast
from fcode.parser.symbol_extractor import extract_symbols
from fcode.contracts import SymbolType


def test_function():
    code = "def hello():\n    pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert len(syms) == 1
    assert syms[0].name == "hello"
    assert syms[0].symbol_type == SymbolType.FUNCTION


def test_async_function():
    code = "async def fetch():\n    pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert len(syms) == 1
    assert syms[0].symbol_type == SymbolType.FUNCTION


def test_class():
    code = "class MyClass:\n    pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert len(syms) == 1
    assert syms[0].name == "MyClass"
    assert syms[0].symbol_type == SymbolType.CLASS


def test_method():
    code = "class Foo:\n    def bar(self):\n        pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert len(syms) == 2
    methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "bar"


def test_async_method():
    code = "class Foo:\n    async def bar(self):\n        pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "bar"


def test_nested_function():
    code = "def outer():\n    def inner():\n        pass\n    pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert len(syms) == 2
    names = {s.name for s in syms}
    assert names == {"outer", "inner"}


def test_duplicate_names():
    code = "def foo(): pass\ndef foo(x): pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    foos = [s for s in syms if s.name == "foo"]
    assert len(foos) == 2


def test_variable():
    code = "x = 42\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    vars_ = [s for s in syms if s.symbol_type == SymbolType.VARIABLE]
    assert len(vars_) == 1
    assert vars_[0].name == "x"


def test_docstring():
    code = 'def foo():\n    """Do stuff."""\n    pass\n'
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert syms[0].docstring == "Do stuff."


def test_empty_module():
    tree = ast.parse("")
    syms = list(extract_symbols(tree, "module.py"))
    assert syms == []


def test_start_line():
    code = "def foo():\n    pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    assert syms[0].start_line == 1


def test_deterministic_ordering():
    code = "def b(): pass\ndef a(): pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    names = [s.name for s in syms]
    assert names == ["b", "a"]


def test_parent_relationship():
    code = "class Outer:\n    class Inner:\n        def method(self): pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    methods = [s for s in syms if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].parent == "Inner"
    assert methods[0].qualified_name == "Outer.Inner.method"


def test_qualified_name():
    code = "class Foo:\n    def bar(self): pass\n"
    tree = ast.parse(code)
    syms = list(extract_symbols(tree, "module.py"))
    method = [s for s in syms if s.symbol_type == SymbolType.METHOD][0]
    assert method.qualified_name == "Foo.bar"
    assert method.parent == "Foo"
