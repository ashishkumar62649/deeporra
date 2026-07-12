"""Small WP6 fixture helpers; production boundaries stay untouched."""

import hashlib
import json
import shutil
import sys
import types
from pathlib import Path

from fcode.chunking.chunker import Chunker
from fcode.contracts import FCodeConfig, RepoInput
from fcode.embeddings.encoder import EXPECTED_DIMENSION, EmbeddingEncoder
from fcode.graph.graph_builder import build
from fcode.indexing.index_service import IndexService
from fcode.parser.python_ast import parse
from fcode.scanner.file_scanner import scan

ROOT = Path(__file__).parents[1] / "fixtures" / "wp6"


class FakeSentenceTransformer:
    """Deterministic local stand-in for the already-supported model seam."""

    inputs: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def get_sentence_embedding_dimension(self):
        return EXPECTED_DIMENSION

    def encode(self, texts, **kwargs):
        self.inputs.extend(texts)
        return [[float(index)] * EXPECTED_DIMENSION for index, _ in enumerate(texts)]


def install_fake_model(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    FakeSentenceTransformer.inputs = []


def analyze(repo: Path, monkeypatch):
    install_fake_model(monkeypatch)
    config = FCodeConfig(repo_path=str(repo))
    scanner = types.SimpleNamespace(scan=scan)
    parser = types.SimpleNamespace(parse=parse)
    graph_builder = types.SimpleNamespace(build=build)
    return IndexService(scanner, parser, Chunker(), encoder=EmbeddingEncoder(), graph_builder=graph_builder).build_through_graphing(config)


def fixture_digest(repo: Path) -> dict:
    files = sorted(path for path in repo.rglob("*") if path.is_file())
    digests = {path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    aggregate = hashlib.sha256("".join(f"{name}:{digest}\n" for name, digest in digests.items()).encode()).hexdigest()
    return {"files": digests, "aggregate": aggregate}


def copy_fixture(name: str, target: Path) -> Path:
    destination = target / name
    shutil.copytree(ROOT / "repos" / name, destination)
    return destination


def generate_repository(root: Path, *, module_count: int, functions_per_module: int, classes_per_module: int, methods_per_class: int, route_count: int, test_count: int, documentation_count: int, configuration_line_count: int, seed: int) -> dict:
    """Create a deterministic performance fixture and its structural formulas."""
    prefix = f"seed_{seed}"
    for module in range(module_count):
        lines = [f"# {prefix}"]
        lines += [f"def function_{module}_{index}():\n    return '{prefix}_{index}'\n" for index in range(functions_per_module)]
        for cls in range(classes_per_module):
            lines.append(f"class Class_{module}_{cls}:")
            lines += [f"    def method_{index}(self):\n        return {index}" for index in range(methods_per_class)] or ["    pass"]
        if module < route_count:
            lines += ["", "@app.get('/generated-%d')" % module, f"def route_{module}():", "    return 'ok'"]
        (root / f"module_{module}.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for index in range(test_count):
        (root / f"test_generated_{index}.py").write_text(f"def test_{index}():\n    assert True\n", encoding="utf-8")
    for index in range(documentation_count):
        (root / f"doc_{index}.md").write_text(f"# {prefix} {index}\n", encoding="utf-8")
    (root / "settings.toml").write_text("\n".join(f"line_{index} = {index}" for index in range(configuration_line_count)) + "\n", encoding="utf-8")
    return {"files": module_count + test_count + documentation_count + 1, "functions": module_count * functions_per_module + route_count + test_count, "classes": module_count * classes_per_module, "methods": module_count * classes_per_module * methods_per_class, "routes": route_count}
