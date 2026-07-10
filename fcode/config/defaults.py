"""Default configuration values."""

DEFAULT_SCHEMA_VERSION = 1

DEFAULT_CONFIG = {
    "schema_version": DEFAULT_SCHEMA_VERSION,
    "embedding": {
        "provider": "sentence_transformers",
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
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

LOCKED_CONFIG_PATHS = [
    ("embedding", "provider"),
    ("embedding", "model_name"),
    ("embedding", "dimension"),
    ("indexing", "full_rebuild"),
    ("privacy", "local_only"),
]

ALLOWED_TOP_KEYS = {
    "schema_version", "repo_id", "repo_path", "index_path",
    "embedding", "storage", "indexing", "privacy",
}
