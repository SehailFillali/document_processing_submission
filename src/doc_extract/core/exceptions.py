"""Custom exceptions with structured error codes."""

from doc_extract.core.error_codes import ErrorCode


class DocExtractError(Exception):
    """Base exception with structured error code."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        details: dict | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.retry_after = retry_after

    def to_dict(self) -> dict:
        """Convert to standardized error response dict."""
        return {
            "error": {
                "code": self.error_code.value,
                "message": self.message,
                "details": self.details,
                "retry_after": self.retry_after,
            }
        }


class ValidationError(DocExtractError):
    """Validation error with specific error codes."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.VAL_MISSING_REQUIRED_FIELD,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, details)


class ProcessingError(DocExtractError):
    """Processing error."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROC_EXTRACTION_FAILED,
        details: dict | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message, error_code, details, retry_after)


class StorageError(DocExtractError):
    """Storage error."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.STORAGE_UPLOAD_FAILED,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, details)


class LLMError(DocExtractError):
    """LLM error with retry information."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.LLM_API_ERROR,
        details: dict | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message, error_code, details, retry_after)


class RateLimitError(DocExtractError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.RATE_LIMIT_EXCEEDED,
        retry_after: float | None = None,
    ):
        super().__init__(message, error_code, {}, retry_after)
