"""Tests for import_extractor.py."""

import ast
from fcode.parser.import_extractor import extract_imports


def test_import_module():
    code = "import os\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert imports[0].module == "os"


def test_import_as():
    code = "import numpy as np\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert imports[0].module == "numpy"
    assert "np" in imports[0].names


def test_multiple_imports():
    code = "import os, sys\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 2
    modules = {i.module for i in imports}
    assert modules == {"os", "sys"}


def test_from_import():
    code = "from collections import defaultdict\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert imports[0].module == "collections"


def test_from_import_as():
    code = "from collections import OrderedDict as OD\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert "OD" in imports[0].names


def test_relative_import():
    code = "from . import utils\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert imports[0].is_relative


def test_relative_import_dots():
    code = "from ..models import User\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 1
    assert imports[0].is_relative
    assert ".." in imports[0].module


def test_line_numbers():
    code = "import os\nimport sys\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert imports[0].start_line == 1
    assert imports[1].start_line == 2


def test_repeated_statements():
    code = "import os\nimport os\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 2


def test_ordering():
    code = "import z\nimport a\nimport m\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    modules = [i.module for i in imports]
    assert modules == ["z", "a", "m"]


def test_no_imports():
    code = "x = 1\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert imports == []


def test_mixed_imports():
    code = "import os\nfrom sys import path\nimport json as j\n"
    tree = ast.parse(code)
    imports = extract_imports(tree)
    assert len(imports) == 3
