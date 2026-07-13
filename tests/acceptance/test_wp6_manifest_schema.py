import copy
import json
from pathlib import Path
import pytest
from tests.support.wp6_manifest import REQUIRED, validate_manifest


def valid():
    return {"fixture_id":"X","fixture_name":"x","purpose":"x","scanned_files":["app.py"],"excluded_files":[],"parse_statuses":[{"path":"app.py","status":"parsed","language":"Python","diagnostic_category":None}],"symbols":[{"semantic_key":"function:app.py:run","kind":"function","qualified_name":"run","path":"app.py","start_line":1,"end_line":2,"parent_semantic_key":None}],"imports":[{"source_path":"app.py","source_module":"app","imported_module":"os","imported_name":None,"alias":None,"kind":"import"}],"routes":[{"method":"GET","route_path":"/x","handler_semantic_key":"function:app.py:run","source_path":"app.py","start_line":1,"end_line":2}],"tests":[{"semantic_key":"test:app.py:run","qualified_name":"test_run","source_path":"app.py","start_line":1,"end_line":2,"referenced_semantic_keys":[]}],"chunks":[{"semantic_key":"function:app.py:run","source_path":"app.py","chunk_type":"function","owner_semantic_key":"function:app.py:run","start_line":1,"end_line":2,"embedding_eligible":True,"skip_reason":None}],"graph_nodes":[{"semantic_key":"file:app.py","kind":"file","qualified_name":"app.py","source_path":"app.py","linked_semantic_key":None},{"semantic_key":"function:app.py:run","kind":"function","qualified_name":"run","source_path":"app.py","linked_semantic_key":"function:app.py:run"}],"graph_edges":[{"source_semantic_key":"file:app.py","target_semantic_key":"function:app.py:run","edge_type":"defines","qualifier":None}],"safe_search_terms":["run"],"warnings":[],"errors":[],"secret_oracle":{"labels":["x"],"sha256_digests":["0"*64],"redaction_markers":["[REDACTED]"],"safe_neighbor_terms":["run"]},"deterministic_invariants":{"ids":"stable"}}


def test_valid_manifest(): validate_manifest(valid())


def _parse_status(path):
    return {"path": path, "status": "parsed", "language": "Python", "diagnostic_category": None}


def test_parse_statuses_use_normalized_path_identity():
    manifest = valid()
    manifest["parse_statuses"] = [_parse_status("app.py"), _parse_status("service.py")]
    validate_manifest(manifest)

    manifest["parse_statuses"].append(_parse_status("app.py"))
    with pytest.raises(ValueError, match="parse_statuses: contains duplicate semantic identity"):
        validate_manifest(manifest)

    manifest["parse_statuses"] = [_parse_status("app.py"), _parse_status("./app.py")]
    with pytest.raises(ValueError, match="parse_statuses: contains duplicate semantic identity"):
        validate_manifest(manifest)


def test_seven_distinct_parse_statuses_are_accepted():
    manifest = valid()
    manifest["parse_statuses"] = [_parse_status(path) for path in (
        "guide.rst", "README.md", "service/__init__.py", "service/helpers.py",
        "service/routes.py", "settings.toml", "tests/TestRoutes.py",
    )]
    validate_manifest(manifest)


def test_actual_g01_manifest_uses_strict_semantic_schema():
    path = Path(__file__).parents[1] / "fixtures" / "wp6" / "manifests" / "python_service.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    assert set(manifest) == REQUIRED
    assert not {"counts", "files_expected_to_scan", "integrity"} & set(manifest)
    assert len(manifest["scanned_files"]) == 7
    assert len(manifest["parse_statuses"]) == 7
    assert len({record["path"] for record in manifest["parse_statuses"]}) == 7
    assert len(manifest["symbols"]) == 11
    assert len(manifest["imports"]) == 4
    assert len(manifest["routes"]) == 2
    assert len(manifest["tests"]) == 1
    assert len(manifest["chunks"]) == 19
    assert len(manifest["graph_nodes"]) == 21
    assert len(manifest["graph_edges"]) == 21
    assert len(manifest["warnings"]) == 0
    assert len(manifest["errors"]) == 0

@pytest.mark.parametrize("case", ["imports","chunks","graph_nodes","graph_edges","unknown","absolute","traversal","range","symbol","route","chunk","node","edge","source","target","parent","owner","secret","fcode","opaque"], ids=str)
def test_invalid_manifest(case):
    m=copy.deepcopy(valid())
    if case in {"imports","chunks","graph_nodes","graph_edges"}: del m[case]
    elif case=="unknown": m["extra"]=1
    elif case in {"absolute","traversal","fcode"}: m["scanned_files"]=[{"absolute":"/x","traversal":"../x","fcode":".fcode/x"}[case]]
    elif case=="range": m["symbols"][0]["start_line"]=3
    elif case in {"symbol","chunk","node"}: m[{"symbol":"symbols","chunk":"chunks","node":"graph_nodes"}[case]].append(copy.deepcopy(m[{"symbol":"symbols","chunk":"chunks","node":"graph_nodes"}[case]][0]))
    elif case=="route": m["routes"].append(copy.deepcopy(m["routes"][0]))
    elif case=="edge": m["graph_edges"].append(copy.deepcopy(m["graph_edges"][0]))
    elif case=="source": m["graph_edges"][0]["source_semantic_key"]="missing"
    elif case=="target": m["graph_edges"][0]["target_semantic_key"]="missing"
    elif case=="parent": m["symbols"][0]["parent_semantic_key"]="missing"
    elif case=="owner": m["chunks"][0]["owner_semantic_key"]="missing"
    elif case=="secret": m["purpose"]="TEST_ONLY_SECRET"
    else: m["symbols"][0]["semantic_key"]="550e8400-e29b-41d4-a716-446655440000"
    with pytest.raises(ValueError): validate_manifest(m)
