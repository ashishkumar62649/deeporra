"""Public API regression checks for complete indexing."""

import inspect
from unittest.mock import MagicMock

from fcode.contracts import FCodeConfig, IndexBuildResult, IndexRunResult, IndexState
from fcode.indexing import IndexService


def test_complete_index_api_is_present_without_constructor_io():
    scanner = MagicMock()
    parser = MagicMock()
    chunker = MagicMock()
    service = IndexService(scanner, parser, chunker)
    assert hasattr(service, "build_complete_index")
    assert hasattr(service, "run_index")
    assert hasattr(service, "get_status")
    assert hasattr(service, "get_counts")
    assert list(inspect.signature(service.build_complete_index).parameters) == ["config"]
    scanner.assert_not_called()
    parser.assert_not_called()
    chunker.assert_not_called()


def test_run_index_returns_one_complete_attempt_result():
    service = IndexService(MagicMock(), MagicMock(), MagicMock())
    expected = IndexRunResult(state=IndexState.COMPLETE)
    service.build_complete_index = MagicMock(return_value=IndexBuildResult(run_result=expected))
    assert service.run_index(FCodeConfig()) is expected
    service.build_complete_index.assert_called_once()
