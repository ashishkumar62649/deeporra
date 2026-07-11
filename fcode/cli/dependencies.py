"""Lazy production composition for one CLI invocation."""

from pathlib import Path

from fcode.chunking import Chunker
from fcode.config.settings import CONFIG_FILE_NAME, load_config
from fcode.contracts import FCodeConfig
from fcode.embeddings import EmbeddingEncoder
from fcode.graph.graph_builder import build
from fcode.indexing import IndexService
from fcode.indexing.status_reader import ActiveStatusReader
from fcode.parser.python_ast import parse
from fcode.scanner.file_scanner import scan


class _Scanner:
    def scan(self, repo, config):
        return scan(repo, config)


class _Parser:
    def parse(self, file):
        return parse(file)


class _GraphBuilder:
    def build(self, parsed_files):
        return build(parsed_files)


def resolve_config(repo_path: str) -> FCodeConfig:
    path = Path(repo_path).resolve()
    if not path.is_dir():
        raise ValueError("Repository path is unavailable.")
    if (path / CONFIG_FILE_NAME).is_file():
        return load_config(str(path))
    return FCodeConfig(repo_path=str(path))


def create_index_service(config: FCodeConfig, *, for_status: bool = False) -> IndexService:
    return IndexService(
        _Scanner(),
        _Parser(),
        Chunker(),
        encoder=None if for_status else EmbeddingEncoder(),
        graph_builder=None if for_status else _GraphBuilder(),
        status_reader=ActiveStatusReader(config.repo_path),
    )
