"""Tests for error codes, exceptions, rate limiting, and structured responses."""

from unittest.mock import MagicMock

import pytest

from doc_extract.api.schemas import ErrorResponse, SuccessResponse
from doc_extract.core.error_codes import (
    ErrorCode,
    get_message_for_error_code,
    get_status_for_error_code,
)
from doc_extract.core.exceptions import (
    DocExtractError,
    LLMError,
    ProcessingError,
    RateLimitError,
    StorageError,
    ValidationError,
)


class TestErrorCodes:
    """Test error code enum and mappings."""

    def test_all_codes_have_status_mapping(self):
        """Every ErrorCode has an HTTP status mapping."""
        for code in ErrorCode:
            status = get_status_for_error_code(code)
            assert isinstance(status, int)
            assert 400 <= status <= 599

    def test_status_mapping_correctness(self):
        """Spot-check key status codes."""
        assert get_status_for_error_code(ErrorCode.AUTH_MISSING_API_KEY) == 401
        assert get_status_for_error_code(ErrorCode.VAL_FILE_TOO_LARGE) == 413
        assert get_status_for_error_code(ErrorCode.RATE_LIMIT_EXCEEDED) == 429
        assert get_status_for_error_code(ErrorCode.LLM_CIRCUIT_OPEN) == 503

    def test_get_message_default(self):
        """Default messages returned for known codes."""
        msg = get_message_for_error_code(ErrorCode.RATE_LIMIT_EXCEEDED)
        assert "slow down" in msg.lower() or "too many" in msg.lower()

    def test_get_message_custom(self):
        """Custom message overrides default."""
        msg = get_message_for_error_code(ErrorCode.VAL_FILE_TOO_LARGE, "custom msg")
        assert msg == "custom msg"

    def test_get_message_unknown_code_fallback(self):
        """Unknown code returns generic message."""
        msg = get_message_for_error_code(ErrorCode.INTERNAL_UNEXPECTED_ERROR)
        assert isinstance(msg, str)


class TestExceptions:
    """Test custom exception classes."""

    def test_doc_extract_error_to_dict(self):
        """DocExtractError serializes to dict."""
        err = DocExtractError(
            message="something broke",
            error_code=ErrorCode.INTERNAL_UNEXPECTED_ERROR,
            details={"key": "value"},
            retry_after=30.0,
        )

        d = err.to_dict()
        assert d["error"]["code"] == "INTERNAL_UNEXPECTED_ERROR"
        assert d["error"]["message"] == "something broke"
        assert d["error"]["details"]["key"] == "value"
        assert d["error"]["retry_after"] == 30.0

    def test_validation_error_defaults(self):
        """ValidationError uses correct default code."""
        err = ValidationError("bad input")
        assert err.error_code == ErrorCode.VAL_MISSING_REQUIRED_FIELD

    def test_processing_error_with_retry(self):
        """ProcessingError supports retry_after."""
        err = ProcessingError("timeout", retry_after=60.0)
        assert err.retry_after == 60.0
        assert err.error_code == ErrorCode.PROC_EXTRACTION_FAILED

    def test_storage_error(self):
        """StorageError uses correct default code."""
        err = StorageError("upload failed")
        assert err.error_code == ErrorCode.STORAGE_UPLOAD_FAILED

    def test_llm_error(self):
        """LLMError uses correct default code."""
        err = LLMError("api error", retry_after=120.0)
        assert err.error_code == ErrorCode.LLM_API_ERROR
        assert err.retry_after == 120.0

    def test_rate_limit_error(self):
        """RateLimitError uses correct default code."""
        err = RateLimitError("too fast", retry_after=60.0)
        assert err.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
        assert err.details == {}


class TestSchemas:
    """Test API response schemas."""

    def test_error_response_from_exception(self):
        """ErrorResponse.from_exception works with DocExtractError."""
        err = DocExtractError("bad", ErrorCode.VAL_FILE_CORRUPTED, {"file": "test.pdf"})
        resp = ErrorResponse.from_exception(err)
        assert resp.error.code == "VAL_FILE_CORRUPTED"
        assert resp.error.message == "bad"

    def test_error_response_from_generic_exception(self):
        """ErrorResponse.from_exception handles generic exceptions."""
        err = RuntimeError("unexpected")
        resp = ErrorResponse.from_exception(err)
        assert resp.error.code == "INTERNAL_UNEXPECTED_ERROR"

    def test_success_response(self):
        """SuccessResponse serializes correctly."""
        resp = SuccessResponse(data={"id": "123"}, meta={"version": "1.0"})
        assert resp.data["id"] == "123"
        assert resp.meta["version"] == "1.0"


class TestRateLimiter:
    """Test rate limiting."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Requests under limit pass through."""
        from doc_extract.core.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(requests_per_minute=10))
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        # Should not raise
        await limiter.check_rate_limit(request)

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        """Requests over limit are blocked."""
        from doc_extract.core.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(requests_per_minute=3))
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        for _ in range(3):
            await limiter.check_rate_limit(request)

        with pytest.raises(RateLimitError):
            await limiter.check_rate_limit(request)

    @pytest.mark.asyncio
    async def test_api_key_client_id(self):
        """API key is used as client ID when present."""
        from doc_extract.core.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(requests_per_minute=2))
        request = MagicMock()
        request.headers = {"X-API-Key": "key123"}
        request.client = MagicMock()

        client_id = limiter._get_client_id(request)
        assert client_id == "key:key123"

    @pytest.mark.asyncio
    async def test_forwarded_for_client_id(self):
        """X-Forwarded-For is used when no API key."""
        from doc_extract.core.rate_limiter import RateLimiter

        limiter = RateLimiter()
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "10.0.0.1, 10.0.0.2"}
        request.client = MagicMock()

        client_id = limiter._get_client_id(request)
        assert client_id == "ip:10.0.0.1"

    def test_remaining_quota(self):
        """Remaining quota is reported correctly."""
        from doc_extract.core.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60))
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        quota = limiter.get_remaining_quota(request)
        assert quota["requests_per_minute_remaining"] == 60


class TestErrorCodesEndpoint:
    """Test error codes API endpoint."""

    def test_error_codes_endpoint(self):
        """GET /api/v1/errors/codes returns all codes."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        client = TestClient(app)
        r = client.get("/api/v1/errors/codes")
        assert r.status_code == 200

        data = r.json()
        codes = data["error_codes"]
        assert len(codes) == len(ErrorCode)

        # Check structure
        first = codes[0]
        assert "code" in first
        assert "http_status" in first
        assert "retryable" in first

    def test_rate_limit_headers_present(self):
        """Rate limit headers are present in responses."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_db = MagicMock()
        mock_db.init_tables = AsyncMock()
        mock_db.query = AsyncMock(
            return_value=MagicMock(items=[], total_count=0, page=1, page_size=20)
        )

        with patch("doc_extract.api.main.db", mock_db):
            client = TestClient(app)
            r = client.get("/api/v1/submissions")
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers
