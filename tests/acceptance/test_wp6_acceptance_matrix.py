import json

from tests.support.wp6_golden import ROOT


def test_matrix_assigns_every_scenario_and_automates_wp61():
    scenarios = json.loads((ROOT / "acceptance_matrix.json").read_text(encoding="utf-8"))["scenarios"]
    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))
    assert {scenario["step"] for scenario in scenarios} == {f"WP6.{index}" for index in range(1, 7)}
    for scenario in scenarios:
        assert {"id", "title", "fixture", "risk", "layer", "evidence", "pass", "failure", "step", "test", "status"} <= scenario.keys()
        assert scenario["status"] == "planned"
    assert all(scenario["test"] for scenario in scenarios if scenario["step"] == "WP6.1")
