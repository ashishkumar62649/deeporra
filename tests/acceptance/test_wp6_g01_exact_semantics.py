"""Exact, persistence-free semantic checks for the G01 golden fixture."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from fcode.chunking.chunker import Chunker
from fcode.contracts import FCodeConfig, FileType, ParseStatus, ParsedFile, RepoInput, SymbolType
from fcode.embeddings.encoder import EmbeddingEncoder, build_embedding_inputs
from fcode.graph.graph_builder import build
from fcode.parser.python_ast import parse
from fcode.scanner.file_scanner import scan
from tests.support.wp6_manifest import validate_manifest


REPO_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "wp6" / "repos" / "python_service"
MANIFEST_PATH = REPO_ROOT / "tests" / "fixtures" / "wp6" / "manifests" / "python_service.json"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _path(value: str) -> str:
    return value.replace("\\", "/")


def _module_name(file_path: str) -> str:
    if file_path.startswith("tests/"):
        return "tests"
    return Path(file_path).stem


def _source_module(file_path: str) -> str:
    return file_path.rsplit("/", 1)[0].replace("/", ".") if "/" in file_path else ""


def _symbol_prefix(symbol, source_file, route_handlers: set[str]) -> str:
    if source_file.file_type == FileType.TEST and symbol.name.startswith("test_"):
        return "test"
    if symbol.symbol_type == SymbolType.FUNCTION:
        source_line = source_file.safe_content.splitlines()[symbol.start_line - 1].lstrip()
        if source_line.startswith("async def ") and symbol.name not in route_handlers:
            return "async_function"
        return "function"
    return symbol.symbol_type.value


def _symbol_key(symbol, parsed_file, source_file, route_handlers: set[str]) -> str:
    return f"{_symbol_prefix(symbol, source_file, route_handlers)}:{_module_name(parsed_file.file_path)}:{symbol.qualified_name or symbol.name}"


def _actual_static(root: Path) -> dict[str, object]:
    config = FCodeConfig(repo_path=str(root))
    scanned = scan(RepoInput(repo_path=str(root)), config)
    source_by_path = {_path(item.file_path): item for item in scanned.files}
    parsed = [
        parse(item)
        for item in scanned.files
        if item.parse_status == ParseStatus.PENDING and not item.is_binary
    ]
    parsed_by_id = {item.file_id: item for item in parsed}
    graph_inputs = [
        parsed_by_id.get(item.file_id)
        or ParsedFile(
            file_path=item.file_path,
            file_type=item.file_type,
            status=item.parse_status,
            file_id=item.file_id,
            line_count=item.line_count,
        )
        for item in scanned.files
    ]
    route_handlers = {
        route.handler_function
        for item in parsed
        for route in item.routes
    }
    symbols_by_id = {}
    symbols = []
    for item in parsed:
        source_file = source_by_path[_path(item.file_path)]
        for symbol in item.symbols:
            if symbol.symbol_type == SymbolType.ROUTE:
                continue
            key = _symbol_key(symbol, item, source_file, route_handlers)
            symbols_by_id[symbol.symbol_id] = key
            if source_file.file_type == FileType.TEST and symbol.name.startswith("test_"):
                symbols_by_id[f"test:{item.file_path}:{symbol.name}:{symbol.start_line}"] = key
            symbols.append(
                {
                    "semantic_key": key,
                    "kind": symbol.symbol_type.value,
                    "qualified_name": symbol.qualified_name or symbol.name,
                    "path": _path(item.file_path),
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                    "parent_semantic_key": (
                        f"class:{_module_name(item.file_path)}:{symbol.parent}"
                        if symbol.parent
                        else None
                    ),
                }
            )

    imports = []
    routes = []
    tests = []
    route_owner_by_id = {}
    for item in parsed:
        source_path = _path(item.file_path)
        source_file = source_by_path[source_path]
        source_lines = source_file.safe_content.splitlines()
        symbol_by_name = {
            symbol.name: symbol
            for symbol in item.symbols
            if symbol.symbol_type != SymbolType.ROUTE
        }
        for imported in item.imports:
            line = source_lines[imported.line_number - 1].lstrip()
            imports.append(
                {
                    "source_path": source_path,
                    "source_module": _source_module(source_path),
                    "imported_module": imported.module_name,
                    "imported_name": imported.imported_names[0] if imported.imported_names else None,
                    "alias": imported.alias,
                    "kind": "from" if line.startswith("from ") else "import",
                }
            )
        for route in item.routes:
            handler = symbol_by_name[route.handler_function]
            owner = symbols_by_id[handler.symbol_id]
            route_owner_by_id[route.route_id] = owner
            routes.append(
                {
                    "method": route.method.value,
                    "route_path": route.route_path,
                    "handler_semantic_key": owner,
                    "source_path": source_path,
                    "start_line": route.start_line,
                    "end_line": handler.end_line,
                }
            )
        if item.file_type == FileType.TEST:
            for symbol in item.symbols:
                if symbol.name.startswith("test_") and symbol.symbol_type != SymbolType.ROUTE:
                    tests.append(
                        {
                            "semantic_key": symbols_by_id[symbol.symbol_id],
                            "qualified_name": symbol.qualified_name or symbol.name,
                            "source_path": source_path,
                            "start_line": symbol.start_line,
                            "end_line": symbol.end_line,
                            "referenced_semantic_keys": [],
                        }
                    )

    chunks = Chunker().chunk(scanned.files, parsed)
    embedding_inputs = build_embedding_inputs(chunks)
    eligibility = {
        item.chunk_id: EmbeddingEncoder._is_eligible(item)
        for item in embedding_inputs
    }
    chunk_records = []
    for chunk in chunks:
        source_path = _path(chunk.file_path)
        if chunk.symbol_id is None:
            semantic_key = f"{chunk.chunk_type.value}:{source_path}:{chunk.start_line}-{chunk.end_line}"
            owner = None
        elif chunk.symbol_id in route_owner_by_id:
            route = next(route for item in parsed for route in item.routes if route.route_id == chunk.symbol_id)
            semantic_key = f"route:{route.method.value}:{route.route_path}:{chunk.start_line}-{chunk.end_line}"
            owner = route_owner_by_id[chunk.symbol_id]
        else:
            symbol = next(
                symbol
                for item in parsed
                for symbol in item.symbols
                if symbol.symbol_id == chunk.symbol_id
            )
            prefix = (
                "test"
                if source_file.file_type == FileType.TEST and symbol.name.startswith("test_")
                else symbol.symbol_type.value
            )
            semantic_key = f"{prefix}:{_module_name(source_path)}:{symbol.qualified_name or symbol.name}:{chunk.start_line}-{chunk.end_line}"
            owner = symbols_by_id[chunk.symbol_id]
        eligible = eligibility[chunk.chunk_id]
        chunk_records.append(
            {
                "semantic_key": semantic_key,
                "source_path": source_path,
                "chunk_type": chunk.chunk_type.value,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "owner_semantic_key": owner,
                "embedding_eligible": eligible,
                "skip_reason": None if eligible else "ineligible",
            }
        )

    graph = build(graph_inputs)
    graph_nodes = []
    node_qualified_names = {}
    for item in parsed:
        for symbol in item.symbols:
            if symbol.symbol_type != SymbolType.ROUTE:
                node_qualified_names[symbol.symbol_id] = symbol.qualified_name or symbol.name
                if source_by_path[_path(item.file_path)].file_type == FileType.TEST and symbol.name.startswith("test_"):
                    node_qualified_names[
                        f"test:{item.file_path}:{symbol.name}:{symbol.start_line}"
                    ] = symbol.qualified_name or symbol.name
    for node in graph.nodes:
        node_id = node.node_id
        linked = None
        qualified_name = node.label
        if node.node_type.value == "route":
            handler = node.metadata.get("handler_function")
            linked = next(
                owner
                for route_id, owner in route_owner_by_id.items()
                if route_id == node_id
            ) if node_id in route_owner_by_id else None
            qualified_name = handler
        elif node_id in symbols_by_id:
            linked = symbols_by_id[node_id]
            qualified_name = node_qualified_names[node_id]
        graph_nodes.append(
            {
                "semantic_key": node_id,
                "kind": node.node_type.value,
                "qualified_name": qualified_name,
                "source_path": _path(node.source_file) if node.source_file else None,
                "linked_semantic_key": linked,
            }
        )
    graph_edges = [
        {
            "source_semantic_key": edge.source_node_id,
            "target_semantic_key": edge.target_node_id,
            "edge_type": edge.relation.value,
            "qualifier": None,
        }
        for edge in graph.edges
    ]
    parse_statuses = []
    for item in scanned.files:
        parsed_file = parsed_by_id.get(item.file_id)
        parse_statuses.append(
            {
                "path": _path(item.file_path),
                "status": parsed_file.status.value if parsed_file else item.parse_status.value,
                "language": item.language.value if hasattr(item.language, "value") else item.language,
                "diagnostic_category": None,
            }
        )
    errors = [error for item in parsed for error in item.errors]
    errors.extend(graph.errors)
    return {
        "scanned_files": sorted(source_by_path),
        "excluded_files": sorted(_path(item.file_path) for item in scanned.skipped),
        "parse_statuses": parse_statuses,
        "symbols": symbols,
        "imports": imports,
        "routes": routes,
        "tests": tests,
        "chunks": chunk_records,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "warnings": list(scanned.warnings),
        "errors": errors,
    }


def _expected() -> dict[str, object]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def _generated_artifacts(root: Path) -> list[str]:
    artifact_names = {".fcode", "chroma", "__pycache__", ".pytest_cache", "cache", "tmp", "active.json"}
    artifact_suffixes = {".db", ".sqlite", ".sqlite3", ".lock"}
    found = []
    for item in root.rglob("*"):
        if item.name in artifact_names or item.suffix.lower() in artifact_suffixes or item.name.startswith("generation-"):
            found.append(_path(str(item.relative_to(root))))
    return sorted(found)


def _identity(collection: str, item: object) -> object:
    if collection in {"scanned_files", "excluded_files", "safe_search_terms"}:
        return item
    if collection == "parse_statuses":
        return item["path"]
    if collection in {"symbols", "tests", "chunks", "graph_nodes"}:
        return item["semantic_key"]
    if collection == "imports":
        return tuple(item[field] for field in ("source_path", "imported_module", "imported_name", "alias", "kind"))
    if collection == "routes":
        return tuple(item[field] for field in ("method", "route_path", "handler_semantic_key"))
    if collection == "graph_edges":
        return tuple(item[field] for field in ("source_semantic_key", "target_semantic_key", "edge_type", "qualifier"))
    raise AssertionError(f"unknown collection: {collection}")


def assert_exact_collection(name: str, actual: list, expected: list) -> None:
    identity = lambda item: _identity(name, item)
    actual_ids = [identity(item) for item in actual]
    expected_ids = [identity(item) for item in expected]
    actual_counts = Counter(actual_ids)
    expected_counts = Counter(expected_ids)
    duplicate_actual = [key for key, count in actual_counts.items() if count > 1]
    missing = [key for key, count in (expected_counts - actual_counts).items() for _ in range(count)]
    unexpected = [key for key, count in (actual_counts - expected_counts).items() for _ in range(count)]
    actual_by_id = {identity(item): item for item in actual if actual_counts[identity(item)] == 1}
    expected_by_id = {identity(item): item for item in expected if expected_counts[identity(item)] == 1}
    mismatches = [
        {"identity": key, "expected": expected_by_id[key], "actual": actual_by_id[key]}
        for key in expected_by_id.keys() & actual_by_id.keys()
        if expected_by_id[key] != actual_by_id[key]
    ]
    if duplicate_actual or missing or unexpected or mismatches:
        raise AssertionError(
            f"COLLECTION={name} EXPECTED_COUNT={len(expected)} ACTUAL_COUNT={len(actual)} "
            f"DUPLICATES={_json(duplicate_actual)} MISSING={_json(missing)} "
            f"UNEXPECTED={_json(unexpected)} FIELD_MISMATCHES={_json(mismatches)}"
        )


def _compare_to_manifest(actual: dict[str, object], expected: dict[str, object]) -> None:
    collections = (
        "scanned_files",
        "excluded_files",
        "parse_statuses",
        "symbols",
        "imports",
        "routes",
        "tests",
        "chunks",
        "graph_nodes",
        "graph_edges",
    )
    for name in collections:
        assert_exact_collection(name, actual[name], expected[name])
    assert actual["warnings"] == expected["warnings"]
    assert actual["errors"] == expected["errors"]
    assert len(expected["safe_search_terms"]) == 17
    node_ids = {item["semantic_key"] for item in actual["graph_nodes"]}
    dangling = [
        edge
        for edge in actual["graph_edges"]
        if edge["source_semantic_key"] not in node_ids or edge["target_semantic_key"] not in node_ids
    ]
    assert not dangling, f"DANGLING_GRAPH_ENDPOINTS={_json(dangling)}"
    symbol_ids = {item["semantic_key"] for item in actual["symbols"]}
    assert all(
        item["parent_semantic_key"] is None or item["parent_semantic_key"] in symbol_ids
        for item in actual["symbols"]
    )
    assert all(
        item["owner_semantic_key"] is None or item["owner_semantic_key"] in symbol_ids
        for item in actual["chunks"]
    )
    assert all(item["embedding_eligible"] and item["skip_reason"] is None for item in actual["chunks"])
    source_constructs = [
        (item["path"], item["start_line"], item["end_line"])
        for item in actual["symbols"]
    ]
    assert len(source_constructs) == len(set(source_constructs)), (
        f"DUPLICATE_SOURCE_CONSTRUCTS={_json(source_constructs)}"
    )


def test_g01_production_semantics_exactly_match_manifest() -> None:
    actual = _actual_static(FIXTURE_ROOT)
    assert not _generated_artifacts(FIXTURE_ROOT), _generated_artifacts(FIXTURE_ROOT)
    _compare_to_manifest(actual, _expected())


def test_g01_semantic_identities_are_parent_directory_independent(tmp_path: Path) -> None:
    first = tmp_path / "first" / "python_service"
    second = tmp_path / "second" / "python_service"
    shutil.copytree(FIXTURE_ROOT, first)
    shutil.copytree(FIXTURE_ROOT, second)
    first_actual = _actual_static(first)
    second_actual = _actual_static(second)
    for name in first_actual:
        if isinstance(first_actual[name], list):
            assert_exact_collection(name, first_actual[name], second_actual[name])
        else:
            assert first_actual[name] == second_actual[name]
    assert str(tmp_path) not in _json(first_actual)
    assert str(tmp_path) not in _json(second_actual)


def test_exact_collection_diff_reports_field_mismatches() -> None:
    with pytest.raises(AssertionError, match="COLLECTION=symbols.*FIELD_MISMATCHES"):
        assert_exact_collection(
            "symbols",
            [{"semantic_key": "symbol:a", "kind": "function"}],
            [{"semantic_key": "symbol:a", "kind": "class"}],
        )
