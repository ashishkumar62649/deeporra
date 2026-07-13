import json

from tests.support.wp6_manifest import validate_manifest
from tests.support.wp6_golden import ROOT, fixture_digest

EXPECTED_FIXTURE_DIGESTS = {
    "python_service": "bba310f73070a23fb804cf5968ec0e530419ccb01ec056c86e1abec8bb44233c",
}


def test_manifests_are_complete_and_fixture_bytes_match():
    manifests = sorted((ROOT / "manifests").glob("*.json"))
    assert {path.stem for path in manifests} == {"python_service", "errors_and_secrets", "paths_and_unicode", "docs_and_config", "relationships_and_duplicates", "empty_repo", "minimal_repo", "non_execution_tripwire"}
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        repo = ROOT / "repos" / manifest["fixture_name"]
        actual_files = sorted(file.relative_to(repo).as_posix() for file in repo.rglob("*") if file.is_file())
        assert all("\\" not in file and not file.startswith("/") for file in actual_files)
        assert manifest["fixture_id"]
        assert manifest["fixture_name"] == path.stem
        if "scanned_files" in manifest:
            validate_manifest(manifest)
            assert actual_files == sorted(manifest["scanned_files"])
            assert fixture_digest(repo)["aggregate"] == EXPECTED_FIXTURE_DIGESTS[path.stem]
        else:
            assert fixture_digest(repo) == manifest["integrity"]


def test_fixture_roots_contain_no_index_artifacts():
    forbidden = {".fcode", "active.json", "rebuild.lock"}
    for path in (ROOT / "repos").rglob("*"):
        assert path.name not in forbidden
        assert not path.name.startswith("generation-")
