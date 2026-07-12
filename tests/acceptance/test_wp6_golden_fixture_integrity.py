import json

from tests.support.wp6_golden import ROOT, fixture_digest


def test_manifests_are_complete_and_fixture_bytes_match():
    manifests = sorted((ROOT / "manifests").glob("*.json"))
    assert {path.stem for path in manifests} == {"python_service", "errors_and_secrets", "paths_and_unicode", "docs_and_config", "relationships_and_duplicates", "empty_repo", "minimal_repo", "non_execution_tripwire"}
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert {"fixture_id", "fixture_name", "purpose", "files_expected_to_scan", "counts", "integrity"} <= manifest.keys()
        assert fixture_digest(ROOT / "repos" / manifest["fixture_name"]) == manifest["integrity"]


def test_fixture_roots_contain_no_index_artifacts():
    forbidden = {".fcode", "active.json", "rebuild.lock"}
    for path in (ROOT / "repos").rglob("*"):
        assert path.name not in forbidden
        assert not path.name.startswith("generation-")
