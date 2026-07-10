"""Configuration loading, validation, and saving."""

import json
import os
from pathlib import Path

from fcode.config.defaults import (
    ALLOWED_TOP_KEYS,
    DEFAULT_CONFIG,
    DEFAULT_SCHEMA_VERSION,
    LOCKED_CONFIG_PATHS,
)
from fcode.contracts import FCodeConfig

CONFIG_FILE_NAME = ".fcode/config.json"


def _config_path(repo_path: str) -> Path:
    return Path(repo_path) / CONFIG_FILE_NAME


def _nested_get(data: dict, keys: tuple) -> object:
    val = data
    for k in keys:
        if not isinstance(val, dict):
            return None
        val = val.get(k)
    return val


def load_config(repo_path: str) -> FCodeConfig:
    path = _config_path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"config_invalid: config file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"config_invalid: cannot read config file \u2014 {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"config_invalid: malformed JSON \u2014 {e}")

    if not isinstance(data, dict):
        raise ValueError("config_invalid: expected a JSON object")

    if "schema_version" not in data:
        raise ValueError("config_invalid: missing schema_version")
    if data["schema_version"] != DEFAULT_SCHEMA_VERSION:
        raise ValueError(
            f"config_invalid: unsupported schema version {data['schema_version']}"
        )

    unknown = set(data.keys()) - ALLOWED_TOP_KEYS
    if unknown:
        raise ValueError(
            f"config_invalid: unknown fields: {', '.join(sorted(unknown))}"
        )

    for keys in LOCKED_CONFIG_PATHS:
        expected = _nested_get(DEFAULT_CONFIG, keys)
        actual = _nested_get(data, keys)
        if actual != expected:
            path_str = "/".join(keys)
            raise ValueError(
                f"config_invalid: locked value '{path_str}' is "
                f"'{actual}', expected '{expected}'"
            )

    embedding = data.get("embedding", {})
    storage = data.get("storage", {})

    return FCodeConfig(
        repo_path=data.get("repo_path", repo_path),
        db_path=os.path.join(
            repo_path, storage.get("sqlite_path", ".fcode/index.db")
        ),
        chroma_path=os.path.join(
            repo_path, storage.get("chroma_path", ".fcode/chroma")
        ),
        embedding_model=embedding.get(
            "model_name", DEFAULT_CONFIG["embedding"]["model_name"]
        ),
        embedding_device="cpu",
    )


def _build_config_json(config: FCodeConfig) -> dict:
    return {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "repo_path": config.repo_path,
        "embedding": {
            "provider": DEFAULT_CONFIG["embedding"]["provider"],
            "model_name": DEFAULT_CONFIG["embedding"]["model_name"],
            "dimension": DEFAULT_CONFIG["embedding"]["dimension"],
        },
        "storage": {
            "sqlite_path": ".fcode/index.db",
            "chroma_path": ".fcode/chroma",
        },
        "indexing": {
            "python_only": True,
            "max_file_size_bytes": 1048576,
            "full_rebuild": True,
        },
        "privacy": {
            "local_only": True,
            "allow_cloud_llm": False,
        },
    }


def save_config(repo_path: str, config: FCodeConfig) -> None:
    target = _config_path(repo_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _build_config_json(config)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(target)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def create_default_config(repo_path: str, force: bool = False) -> FCodeConfig:
    path = _config_path(repo_path)
    if path.exists() and not force:
        raise FileExistsError(f"Config file already exists: {path}")
    config = FCodeConfig(repo_path=repo_path)
    save_config(repo_path, config)
    return config
