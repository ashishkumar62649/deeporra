"""In-process doctor command tests — verify diagnostic content without repeated subprocess launches."""

from fcode.utils.health import run_doctor


class TestDoctorDiagnostics:
    def test_doctor_shows_check_results(self):
        result = run_doctor()
        for check in result.checks:
            assert check.passed in (True, False)

    def test_doctor_python_version_check(self):
        result = run_doctor()
        names = {c.name for c in result.checks}
        assert "python_version" in names

    def test_doctor_required_imports_check(self):
        result = run_doctor()
        names = {c.name for c in result.checks}
        assert "required_imports" in names
