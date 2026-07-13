"""Offline doctor readiness checks."""

import socket
import sys

from typer.testing import CliRunner

from fcode.cli.main import app
from fcode.contracts import DiagnosticSeverity, DoctorCheck, DoctorResult
from fcode.utils import health


def test_doctor_ready_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "check_required_imports", lambda: DoctorCheck("required_imports", True, "all available", DiagnosticSeverity.WARNING))
    monkeypatch.setattr(health, "check_sqlite_fts5", lambda: DoctorCheck("sqlite_fts5", True, "available", DiagnosticSeverity.WARNING))
    monkeypatch.setattr(health, "check_local_embedding_model", lambda: DoctorCheck("local_embedding_model", True, "available", DiagnosticSeverity.WARNING))
    assert health.run_doctor(str(tmp_path)).all_passed


def test_missing_sentence_transformers_is_actionable(monkeypatch):
    monkeypatch.setattr(health.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError()) if name == "sentence_transformers" else object())
    check = health.check_required_imports()
    assert not check.passed and "sentence_transformers" in check.message


def test_missing_chromadb_is_actionable(monkeypatch):
    monkeypatch.setattr(health.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError()) if name == "chromadb" else object())
    check = health.check_required_imports()
    assert not check.passed and "chromadb" in check.message


def test_missing_local_model_reports_exception_type(monkeypatch):
    class Encoder:
        def ensure_available(self):
            raise RuntimeError("C:/private/cache/token")
    monkeypatch.setattr("fcode.embeddings.EmbeddingEncoder", Encoder)
    check = health.check_local_embedding_model()
    assert not check.passed
    assert "Local embedding model is unavailable" in check.message
    assert "RuntimeError" in check.message
    assert "private" not in check.message


def test_required_imports_includes_interpreter(monkeypatch):
    monkeypatch.setattr(health.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError()) if name == "sentence_transformers" else object())
    check = health.check_required_imports()
    assert "interpreter:" in check.message
    assert sys.executable in check.message


def test_local_model_error_includes_type(monkeypatch):
    class Encoder:
        def ensure_available(self):
            raise ValueError("something broke")
    monkeypatch.setattr("fcode.embeddings.EmbeddingEncoder", Encoder)
    check = health.check_local_embedding_model()
    assert "ValueError" in check.message


def test_fts_unavailable_is_reported(monkeypatch):
    monkeypatch.setattr(health.sqlite3, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(health.sqlite3.DatabaseError()))
    assert not health.check_sqlite_fts5().passed


def test_doctor_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(
        "fcode.cli.commands.doctor_cmd.run_doctor",
        lambda **_: DoctorResult([DoctorCheck("local_embedding_model", False, "Local embedding model is unavailable", DiagnosticSeverity.ERROR)]),
    )
    result = CliRunner().invoke(app, ["doctor", "."])
    assert result.exit_code == 1
    assert "Local embedding model is unavailable" in result.output
    assert "Traceback" not in result.output
