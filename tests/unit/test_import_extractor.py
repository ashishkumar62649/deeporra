"""Tests for import_extractor.py."""

import ast
from fcode.parser.import_extractor import extract_imports


def test_import_module():
    code = "import os\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 1
    assert imports[0].module_name == "os"


def test_import_as():
    code = "import numpy as np\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 1
    assert imports[0].module_name == "numpy"
    assert "np" in imports[0].imported_names


def test_multiple_imports():
    code = "import os, sys\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 2
    modules = {i.module_name for i in imports}
    assert modules == {"os", "sys"}


def test_from_import():
    code = "from collections import defaultdict\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 1
    assert imports[0].module_name == "collections"


def test_from_import_as():
    code = "from collections import OrderedDict as OD\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 1
    assert "OD" in imports[0].imported_names


def test_line_numbers():
    code = "import os\nimport sys\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert imports[0].line_number == 1
    assert imports[1].line_number == 2


def test_repeated_statements():
    code = "import os\nimport os\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 2


def test_ordering():
    code = "import z\nimport a\nimport m\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    modules = [i.module_name for i in imports]
    assert modules == ["z", "a", "m"]


def test_no_imports():
    code = "x = 1\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert imports == []


def test_mixed_imports():
    code = "import os\nfrom sys import path\nimport json as j\n"
    tree = ast.parse(code)
    imports = list(extract_imports(tree, "mod.py"))
    assert len(imports) == 3
