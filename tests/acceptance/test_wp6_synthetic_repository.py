from tests.support.wp6_golden import fixture_digest, generate_repository


def test_generator_is_deterministic_and_reports_its_formula(tmp_path):
    params = dict(module_count=3, functions_per_module=2, classes_per_module=1, methods_per_class=2, route_count=2, test_count=2, documentation_count=1, configuration_line_count=101, seed=7)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    formula = generate_repository(first, **params)
    assert generate_repository(second, **params) == formula
    assert fixture_digest(first) == fixture_digest(second)
    assert formula == {"files": 7, "functions": 10, "classes": 3, "methods": 6, "routes": 2}
