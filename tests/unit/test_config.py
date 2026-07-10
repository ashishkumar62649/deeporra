"""Configuration tests — verify fcode/config/ module."""

import copy
import json
from pathlib import Path

import pytest

from fcode.config.defaults import (
    ALLOWED_TOP_KEYS,
    DEFAULT_CONFIG,
    DEFAULT_SCHEMA_VERSION,
    LOCKED_CONFIG_PATHS,
)
from fcode.config.settings import (
    CONFIG_FILE_NAME,
    create_default_config,
    load_config,
    save_config,
)
from fcode.contracts import FCodeConfig


def _fresh_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def _write_config(repo_path: str, data: dict) -> Path:
    path = Path(repo_path) / CONFIG_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestDefaults:
    def test_default_schema_version(self):
        assert DEFAULT_SCHEMA_VERSION == 1

    def test_default_config_has_schema_version(self):
        assert DEFAULT_CONFIG["schema_version"] == 1

    def test_locked_config_paths(self):
        expected = [
            ("embedding", "provider"),
            ("embedding", "model_name"),
            ("embedding", "dimension"),
            ("indexing", "full_rebuild"),
            ("privacy", "local_only"),
        ]
        assert LOCKED_CONFIG_PATHS == expected

    def test_allowed_top_keys(self):
        for key in ("schema_version", "repo_id", "repo_path", "embedding",
                    "storage", "indexing", "privacy"):
            assert key in ALLOWED_TOP_KEYS


class TestLoadConfig:
    def test_default_config_matches_fcode_config_defaults(self):
        cfg = FCodeConfig()
        assert cfg.repo_path == "."
        assert cfg.embedding_device == "cpu"

    def test_valid_config_loads(self, tmp_path: Path):
        data = _fresh_config()
        data["repo_path"] = str(tmp_path)
        _write_config(str(tmp_path), data)
        cfg = load_config(str(tmp_path))
        assert isinstance(cfg, FCodeConfig)
        assert cfg.embedding_device == "cpu"

    def test_malformed_json_fails(self, tmp_path: Path):
        path = Path(tmp_path) / CONFIG_FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match=r"config_invalid:.*malformed JSON"):
            load_config(str(tmp_path))

    def test_unknown_fields_fail(self, tmp_path: Path):
        data = _fresh_config()
        data["unknown_field"] = "value"
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*unknown field"):
            load_config(str(tmp_path))

    def test_unsupported_schema_version_fails(self, tmp_path: Path):
        data = _fresh_config()
        data["schema_version"] = 99
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*unsupported schema version"):
            load_config(str(tmp_path))

    def test_alternate_model_fails(self, tmp_path: Path):
        data = _fresh_config()
        data["embedding"]["model_name"] = "other-model"
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*locked value"):
            load_config(str(tmp_path))

    def test_alternate_dimension_fails(self, tmp_path: Path):
        data = _fresh_config()
        data["embedding"]["dimension"] = 768
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*locked value"):
            load_config(str(tmp_path))

    def test_alternate_embedding_provider_fails(self, tmp_path: Path):
        data = _fresh_config()
        data["embedding"]["provider"] = "openai"
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*locked value"):
            load_config(str(tmp_path))

    def test_alternate_full_rebuild_fails(self, tmp_path: Path):
        data = _fresh_config()
        data["indexing"]["full_rebuild"] = False
        _write_config(str(tmp_path), data)
        with pytest.raises(ValueError, match=r"config_invalid:.*locked value"):
            load_config(str(tmp_path))

    def test_nonexistent_config_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="config_invalid"):
            load_config(str(tmp_path))


class TestSaveConfig:
    def test_save_and_relaod_roundtrip(self, tmp_path: Path):
        cfg = FCodeConfig(repo_path=str(tmp_path))
        save_config(str(tmp_path), cfg)
        result = load_config(str(tmp_path))
        assert result.embedding_device == "cpu"
        assert "all-MiniLM-L6-v2" in result.embedding_model

    def test_atomic_save_creates_no_temp(self, tmp_path: Path):
        cfg = FCodeConfig(repo_path=str(tmp_path))
        save_config(str(tmp_path), cfg)
        target = Path(tmp_path) / CONFIG_FILE_NAME
        assert target.exists()
        tmp_files = list(tmp_path.rglob("*.tmp"))
        assert len(tmp_files) == 0

    def test_existing_config_not_overwritten(self, tmp_path: Path):
        _write_config(str(tmp_path), _fresh_config())
        with pytest.raises(FileExistsError):
            create_default_config(str(tmp_path))


class TestCreateDefault:
    def test_create_default_returns_fcode_config(self, tmp_path: Path):
        cfg = create_default_config(str(tmp_path))
        assert isinstance(cfg, FCodeConfig)

    def test_create_default_creates_file(self, tmp_path: Path):
        create_default_config(str(tmp_path))
        assert (Path(tmp_path) / CONFIG_FILE_NAME).exists()

    def test_create_default_force_overwrites(self, tmp_path: Path):
        create_default_config(str(tmp_path))
        cfg = create_default_config(str(tmp_path), force=True)
        assert isinstance(cfg, FCodeConfig)
