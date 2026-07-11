"""Error code tests — verify ErrorCode and McpErrorCode conventions."""

from fcode.contracts.errors import ErrorCode, McpErrorCode


class TestErrorCodeContract:
    def test_all_lowercase_snake(self):
        for member in ErrorCode:
            val = member.value
            assert val == val.lower(), f"{val} must be lowercase"
            assert "_" in val or " " not in val, f"{val} should be snake_case"

    def test_mcp_all_lowercase_snake(self):
        for member in McpErrorCode:
            val = member.value
            assert val == val.lower(), f"{val} must be lowercase"

    def test_error_codes_enum_values(self):
        assert ErrorCode.REPOSITORY_LIMIT_EXCEEDED.value == "repository_limit_exceeded"
        assert ErrorCode.FILE_SKIPPED.value == "file_skipped"
        assert ErrorCode.PARSE_FAILED.value == "parse_failed"
        assert ErrorCode.PERSIST_FAILED.value == "persist_failed"
        assert ErrorCode.UNEXPECTED_ERROR.value == "unexpected_error"
        assert ErrorCode.NOT_IMPLEMENTED.value == "not_implemented"
        assert ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value == "embedding_model_unavailable"
        assert ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value == "embedding_dimension_mismatch"
        assert ErrorCode.EMBEDDING_ALL_CHUNKS_FAILED.value == "embedding_all_chunks_failed"
        assert ErrorCode.EMBEDDING_CHUNK_WARNING.value == "embedding_chunk_warning"

    def test_mcp_error_code_values(self):
        assert McpErrorCode.INVALID_INPUT.value == "invalid_input"
        assert McpErrorCode.NO_INDEX.value == "no_index"
        assert McpErrorCode.INDEX_IN_PROGRESS.value == "index_in_progress"
        assert McpErrorCode.TOOL_NOT_FOUND.value == "tool_not_found"
