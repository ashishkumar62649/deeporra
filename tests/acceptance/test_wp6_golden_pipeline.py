import json
import shutil

import pytest

from tests.support.wp6_golden import FakeSentenceTransformer, ROOT, analyze, copy_fixture


def _manifest(name):
    return json.loads((ROOT / "manifests" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [path.stem for path in sorted((ROOT / "manifests").glob("*.json"))])
def test_golden_manifest_matches_static_pipeline(name, monkeypatch):
    manifest = _manifest(name)
    result = analyze(ROOT / "repos" / name, monkeypatch)
    assert result.run_result.state.value == "graphing"
    assert [file.file_path for file in result.scan_result.files] == manifest["files_expected_to_scan"]
    for field, expected in manifest["counts"].items():
        assert getattr(result.run_result.counts, field) == expected
    statuses = {parsed.file_path: parsed.status.value for parsed in result.parsed_files}
    assert statuses.items() >= manifest.get("parse_status", {}).items()
    symbols = {symbol.qualified_name or symbol.name for parsed in result.parsed_files for symbol in parsed.symbols}
    assert set(manifest.get("symbols", [])) <= symbols
    routes = {(route.method.value, route.route_path, route.handler_function, parsed.file_path) for parsed in result.parsed_files for route in parsed.routes}
    assert set(map(tuple, manifest.get("routes", []))) <= routes
    chunks = {(chunk.file_path, chunk.chunk_type.value, chunk.start_line, chunk.end_line) for chunk in result.chunks}
    for path, start, end in manifest.get("chunk_ranges", []):
        assert any(chunk[0] == path and chunk[2:] == (start, end) for chunk in chunks)
    assert not {chunk.file_path for chunk in result.chunks} & set(manifest.get("excluded_chunk_paths", []))
    node_ids = [node.node_id for node in result.graph_result.nodes]
    edges = [(edge.source_node_id, edge.target_node_id, edge.relation.value) for edge in result.graph_result.edges]
    assert len(node_ids) == len(set(node_ids))
    assert len(edges) == len(set(edges))
    assert {endpoint for edge in edges for endpoint in edge[:2]} <= set(node_ids)


def test_secrets_are_redacted_before_chunking_and_embedding(monkeypatch):
    result = analyze(ROOT / "repos" / "errors_and_secrets", monkeypatch)
    raw_values = [line.split('"')[1] for path in (ROOT / "repos" / "errors_and_secrets").glob("*.*") for line in path.read_text(encoding="utf-8").splitlines() if "TEST_ONLY_" in line]
    content = "\n".join(chunk.content for chunk in result.chunks)
    assert "[REDACTED]" in content
    assert all(value not in content for value in raw_values)
    assert all(value not in FakeSentenceTransformer.inputs for value in raw_values)


def test_tripwire_is_analyzed_without_execution(monkeypatch, tmp_path):
    repo = copy_fixture("non_execution_tripwire", tmp_path)
    sentinel = repo / "TRIPWIRE_EXECUTED"
    result = analyze(repo, monkeypatch)
    assert result.run_result.state.value == "graphing"
    assert not sentinel.exists()


def test_ids_are_independent_of_temporary_directory(monkeypatch, tmp_path):
    first = analyze(copy_fixture("paths_and_unicode", tmp_path / "one"), monkeypatch)
    second = analyze(copy_fixture("paths_and_unicode", tmp_path / "two"), monkeypatch)
    assert [file.file_id for file in first.scan_result.files] == [file.file_id for file in second.scan_result.files]
    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
    assert [node.node_id for node in first.graph_result.nodes] == [node.node_id for node in second.graph_result.nodes]
    assert [edge.record_id for edge in first.graph_result.edges] == [edge.record_id for edge in second.graph_result.edges]
