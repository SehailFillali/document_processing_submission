# Prompt 20: Structured Error Codes & Rate Limiting

## Status
[COMPLETED]

## Context

We need a comprehensive, structured error handling methodology with enum-based error codes and production-grade rate limiting. This demonstrates "Head of Engineering" thinking about API design and operational excellence.

## Objective

Implement:
1. Structured error code enum with categories
2. Rate limiting middleware
3. Standardized error responses
4. Error code documentation

## Requirements

### 1. Create Error Code Enum

File: `src/doc_extract/core/error_codes.py`

```python
"""Structured error codes for the document extraction system.

Provides a comprehensive enum of error codes for programmatic handling
and clear debugging.
"""
from enum import Enum


class ErrorCode(str, Enum):
    """Structured error codes for the system.
    
    Each code has a category prefix:
    - AUTH: Authentication/Authorization
    - VAL: Validation errors
    - PROC: Processing errors
    - STORAGE: Storage/retrieval errors
    - LLM: LLM/extraction errors
    - RATE: Rate limiting errors
    - INTERNAL: Internal system errors
    """
    
    # Authentication/Authorization
    AUTH_MISSING_API_KEY = "AUTH_MISSING_API_KEY"
    AUTH_INVALID_API_KEY = "AUTH_INVALID_API_KEY"
    AUTH_EXPIRED_TOKEN = "AUTH_EXPIRED_TOKEN"
    
    # Validation Errors (VAL)
    VAL_FILE_TOO_LARGE = "VAL_FILE_TOO_LARGE"
    VAL_UNSUPPORTED_FILE_TYPE = "VAL_UNSUPPORTED_FILE_TYPE"
    VAL_FILE_CORRUPTED = "VAL_FILE_CORRUPTED"
    VAL_FILE_PASSWORD_PROTECTED = "VAL_FILE_PASSWORD_PROTECTED"
    VAL_MISSING_REQUIRED_FIELD = "VAL_MISSING_REQUIRED_FIELD"
    VAL_INVALID_FIELD_FORMAT = "VAL_INVALID_FIELD_FORMAT"
    VAL_INVALID_URI_SCHEME = "VAL_INVALID_URI_SCHEME"
    
    # Processing Errors (PROC)
    PROC_EXTRACTION_FAILED = "PROC_EXTRACTION_FAILED"
    PROC_VALIDATION_FAILED = "PROC_VALIDATION_FAILED"
    PROC_TIMEOUT = "PROC_TIMEOUT"
    PROC_STORAGE_ERROR = "PROC_STORAGE_ERROR"
    
    # Storage Errors (STORAGE)
    STORAGE_FILE_NOT_FOUND = "STORAGE_FILE_NOT_FOUND"
    STORAGE_UPLOAD_FAILED = "STORAGE_UPLOAD_FAILED"
    STORAGE_DELETE_FAILED = "STORAGE_DELETE_FAILED"
    STORAGE_BUCKET_NOT_FOUND = "STORAGE_BUCKET_NOT_FOUND"
    
    # LLM Errors (LLM)
    LLM_API_ERROR = "LLM_API_ERROR"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_QUOTA_EXCEEDED = "LLM_QUOTA_EXCEEDED"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    LLM_CIRCUIT_OPEN = "LLM_CIRCUIT_OPEN"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_MODEL_UNAVAILABLE = "LLM_MODEL_UNAVAILABLE"
    
    # Rate Limiting (RATE)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RATE_DAILY_QUOTA_EXCEEDED = "RATE_DAILY_QUOTA_EXCEEDED"
    
    # Internal Errors (INTERNAL)
    INTERNAL_UNEXPECTED_ERROR = "INTERNAL_UNEXPECTED_ERROR"
    INTERNAL_DATABASE_ERROR = "INTERNAL_DATABASE_ERROR"
    INTERNAL_CONFIGURATION_ERROR = "INTERNAL_CONFIGURATION_ERROR"
    INTERNAL_DEPENDENCY_MISSING = "INTERNAL_DEPENDENCY_MISSING"


# Error code to HTTP status mapping
ERROR_CODE_TO_STATUS = {
    # Auth
    ErrorCode.AUTH_MISSING_API_KEY: 401,
    ErrorCode.AUTH_INVALID_API_KEY: 401,
    ErrorCode.AUTH_EXPIRED_TOKEN: 401,
    
    # Validation
    ErrorCode.VAL_FILE_TOO_LARGE: 413,
    ErrorCode.VAL_UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.VAL_FILE_CORRUPTED: 422,
    ErrorCode.VAL_FILE_PASSWORD_PROTECTED: 422,
    ErrorCode.VAL_MISSING_REQUIRED_FIELD: 400,
    ErrorCode.VAL_INVALID_FIELD_FORMAT: 400,
    ErrorCode.VAL_INVALID_URI_SCHEME: 400,
    
    # Processing
    ErrorCode.PROC_EXTRACTION_FAILED: 500,
    ErrorCode.PROC_VALIDATION_FAILED: 422,
    ErrorCode.PROC_TIMEOUT: 504,
    ErrorCode.PROC_STORAGE_ERROR: 500,
    
    # Storage
    ErrorCode.STORAGE_FILE_NOT_FOUND: 404,
    ErrorCode.STORAGE_UPLOAD_FAILED: 500,
    ErrorCode.STORAGE_DELETE_FAILED: 500,
    ErrorCode.STORAGE_BUCKET_NOT_FOUND: 500,
    
    # LLM
    ErrorCode.LLM_API_ERROR: 502,
    ErrorCode.LLM_RATE_LIMITED: 429,
    ErrorCode.LLM_QUOTA_EXCEEDED: 402,
    ErrorCode.LLM_INVALID_RESPONSE: 502,
    ErrorCode.LLM_CIRCUIT_OPEN: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_MODEL_UNAVAILABLE: 503,
    
    # Rate Limiting
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.RATE_DAILY_QUOTA_EXCEEDED: 429,
    
    # Internal
    ErrorCode.INTERNAL_UNEXPECTED_ERROR: 500,
    ErrorCode.INTERNAL_DATABASE_ERROR: 500,
    ErrorCode.INTERNAL_CONFIGURATION_ERROR: 500,
    ErrorCode.INTERNAL_DEPENDENCY_MISSING: 500,
}


# Error code to user-friendly messages
ERROR_CODE_MESSAGES = {
    ErrorCode.VAL_FILE_TOO_LARGE: "The uploaded file exceeds the maximum allowed size",
    ErrorCode.VAL_UNSUPPORTED_FILE_TYPE: "The file type is not supported",
    ErrorCode.VAL_FILE_CORRUPTED: "The file appears to be corrupted",
    ErrorCode.VAL_FILE_PASSWORD_PROTECTED: "Password-protected files are not supported",
    ErrorCode.STORAGE_FILE_NOT_FOUND: "The requested file was not found",
    ErrorCode.LLM_RATE_LIMITED: "The LLM service is rate-limited. Please try again later",
    ErrorCode.LLM_QUOTA_EXCEEDED: "Monthly LLM quota has been exceeded",
    ErrorCode.LLM_CIRCUIT_OPEN: "The LLM service is temporarily unavailable",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests. Please slow down",
    ErrorCode.RATE_DAILY_QUOTA_EXCEEDED: "Daily request quota has been exceeded",
}


def get_status_for_error_code(error_code: ErrorCode) -> int:
    """Get HTTP status code for an error code."""
    return ERROR_CODE_TO_STATUS.get(error_code, 500)


def get_message_for_error_code(error_code: ErrorCode, custom_message: str | None = None) -> str:
    """Get user-friendly message for an error code."""
    if custom_message:
        return custom_message
    return ERROR_CODE_MESSAGES.get(error_code, "An unexpected error occurred")
```

### 2. Update Custom Exceptions

File: `src/doc_extract/core/exceptions.py` (update existing)

```python
"""Custom exceptions with structured error codes."""
from doc_extract.core.error_codes import ErrorCode


class DocExtractError(Exception):
    """Base exception with structured error code."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        details: dict | None = None,
        retry_after: float | None = None
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
                "retry_after": self.retry_after
            }
        }


# Specific exceptions using ErrorCode enum
class ValidationError(DocExtractError):
    """Validation error with specific error codes."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.VAL_MISSING_REQUIRED_FIELD,
        details: dict | None = None
    ):
        super().__init__(message, error_code, details)


class ProcessingError(DocExtractError):
    """Processing error."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROC_EXTRACTION_FAILED,
        details: dict | None = None,
        retry_after: float | None = None
    ):
        super().__init__(message, error_code, details, retry_after)


class StorageError(DocExtractError):
    """Storage error."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.STORAGE_UPLOAD_FAILED,
        details: dict | None = None
    ):
        super().__init__(message, error_code, details)


class LLMError(DocExtractError):
    """LLM error with retry information."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.LLM_API_ERROR,
        details: dict | None = None,
        retry_after: float | None = None
    ):
        super().__init__(message, error_code, details, retry_after)


class RateLimitError(DocExtractError):
    """Rate limit exceeded."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.RATE_LIMIT_EXCEEDED,
        retry_after: float | None = None
    ):
        super().__init__(message, error_code, {}, retry_after)
```

### 3. Create Rate Limiting Middleware

File: `src/doc_extract/core/rate_limiter.py`

```python
"""Rate limiting middleware using token bucket algorithm."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from doc_extract.core.error_codes import ErrorCode, get_status_for_error_code
from doc_extract.core.exceptions import RateLimitError
from doc_extract.core.logging import logger


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_allowance: int = 10


@dataclass
class RateLimitStats:
    """Rate limit statistics for a client."""
    request_count: int = 0
    first_request_time: float = field(default_factory=time.time)
    last_request_time: float = 0
    minute_requests: list = field(default_factory=list)
    hour_requests: list = field(default_factory=list)


class RateLimiter:
    """Token bucket rate limiter with multiple time windows."""
    
    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._clients: dict[str, RateLimitStats] = defaultdict(RateLimitStats)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier (IP or API key)."""
        # Use API key if present, otherwise use IP
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key}"
        
        # Fall back to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0]}"
        
        return f"ip:{request.client.host if request.client else 'unknown'}"
    
    def _cleanup_old_requests(self, stats: RateLimitStats, current_time: float) -> None:
        """Remove requests outside the time windows."""
        # Keep requests from last minute
        stats.minute_requests = [
            t for t in stats.minute_requests
            if current_time - t < 60
        ]
        
        # Keep requests from last hour
        stats.hour_requests = [
            t for t in stats.hour_requests
            if current_time - t < 3600
        ]
    
    async def check_rate_limit(self, request: Request) -> None:
        """Check if request is within rate limits.
        
        Raises:
            RateLimitError: If any limit is exceeded
        """
        client_id = self._get_client_id(request)
        current_time = time.time()
        
        stats = self._clients[client_id]
        self._cleanup_old_requests(stats, current_time)
        
        # Check per-minute limit
        if len(stats.minute_requests) >= self.config.requests_per_minute:
            logger.warning(f"Rate limit exceeded (per-minute) for {client_id}")
            raise RateLimitError(
                message=f"Rate limit: {self.config.requests_per_minute} requests per minute",
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                retry_after=60.0
            )
        
        # Check per-hour limit
        if len(stats.hour_requests) >= self.config.requests_per_hour:
            logger.warning(f"Rate limit exceeded (per-hour) for {client_id}")
            raise RateLimitError(
                message=f"Rate limit: {self.config.requests_per_hour} requests per hour",
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                retry_after=3600.0
            )
        
        # Check per-day limit
        day_requests = sum(
            1 for t in stats.hour_requests
            if current_time - t < 86400
        )
        if day_requests >= self.config.requests_per_day:
            logger.warning(f"Rate limit exceeded (per-day) for {client_id}")
            raise RateLimitError(
                message=f"Daily limit: {self.config.requests_per_day} requests per day",
                error_code=ErrorCode.RATE_DAILY_QUOTA_EXCEEDED,
                retry_after=86400.0
            )
        
        # Record this request
        stats.minute_requests.append(current_time)
        stats.hour_requests.append(current_time)
        stats.request_count += 1
        stats.last_request_time = current_time
    
    def get_remaining_quota(self, request: Request) -> dict:
        """Get remaining quota for the client."""
        client_id = self._get_client_id(request)
        current_time = time.time()
        
        stats = self._clients.get(client_id, RateLimitStats())
        self._cleanup_old_requests(stats, current_time)
        
        return {
            "requests_per_minute_remaining": max(
                0, self.config.requests_per_minute - len(stats.minute_requests)
            ),
            "requests_per_hour_remaining": max(
                0, self.config.requests_per_hour - len(stats.hour_requests)
            ),
            "reset_in_seconds": 60 - (current_time % 60)
        }


# Global rate limiter
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting."""
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/ready", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        try:
            await rate_limiter.check_rate_limit(request)
        except RateLimitError as e:
            from fastapi.responses import JSONResponse
            
            status_code = get_status_for_error_code(e.error_code)
            
            return JSONResponse(
                status_code=status_code,
                content=e.to_dict(),
                headers={"Retry-After": str(e.retry_after)} if e.retry_after else {}
            )
        
        response = await call_next(request)
        
        # Add rate limit headers
        quota = rate_limiter.get_remaining_quota(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(quota["requests_per_minute_remaining"])
        
        return response
```

### 4. Create Error Response Schema

File: `src/doc_extract/api/schemas.py`

```python
"""API response schemas including standardized error format."""
from typing import Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error context"
    )
    retry_after: float | None = Field(
        None,
        description="Seconds to wait before retrying"
    )


class ErrorResponse(BaseModel):
    """Standardized error response."""
    
    error: ErrorDetail
    
    @classmethod
    def from_exception(cls, exc: Exception) -> "ErrorResponse":
        """Create error response from exception."""
        if hasattr(exc, "to_dict"):
            data = exc.to_dict()
            return cls(**data)
        
        return cls(
            error=ErrorDetail(
                code="INTERNAL_UNEXPECTED_ERROR",
                message=str(exc)
            )
        )


class SuccessResponse(BaseModel):
    """Standard success response."""
    
    data: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel):
    """Paginated response."""
    
    data: list[dict[str, Any]]
    pagination: dict[str, Any] = Field(
        ...,
        description="Pagination metadata"
    )
```

### 5. Update API Main with Rate Limiting

File: `src/doc_extract/api/main.py`

```python
# Add imports
from doc_extract.core.rate_limiter import RateLimitMiddleware
from doc_extract.core.error_codes import ErrorCode, get_status_for_error_code
from doc_extract.api.schemas import ErrorResponse

# Add rate limiting middleware (after CORS)
app.add_middleware(RateLimitMiddleware)

# Update exception handler for structured errors
@app.exception_handler(DocExtractError)
async def doc_extract_exception_handler(request: Request, exc: DocExtractError):
    """Handle custom application exceptions with structured error codes."""
    status_code = get_status_for_error_code(exc.error_code)
    
    logger.error(
        f"Error {exc.error_code.value}: {exc.message}",
        extra={"details": exc.details}
    )
    
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after))
    
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
        headers=headers
    )

# Add error code documentation endpoint
@app.get("/api/v1/errors/codes")
async def get_error_codes():
    """Get list of all possible error codes."""
    from doc_extract.core.error_codes import ErrorCode, ERROR_CODE_MESSAGES
    
    return {
        "error_codes": [
            {
                "code": ec.value,
                "description": ERROR_CODE_MESSAGES.get(ec, ""),
                "http_status": get_status_for_error_code(ec),
                "retryable": ec in [
                    ErrorCode.LLM_RATE_LIMITED,
                    ErrorCode.LLM_CIRCUIT_OPEN,
                    ErrorCode.RATE_LIMIT_EXCEEDED,
                ]
            }
            for ec in ErrorCode
        ]
    }
```

## Deliverables

- [ ] src/doc_extract/core/error_codes.py - Error code enum and mappings
- [ ] src/doc_extract/core/exceptions.py - Updated with ErrorCode enum
- [ ] src/doc_extract/core/rate_limiter.py - Rate limiting middleware
- [ ] src/doc_extract/api/schemas.py - Standardized response schemas
- [ ] src/doc_extract/api/main.py - Add middleware and update handler

## Success Criteria

1. All errors return structured response with ErrorCode enum
2. Rate limiting blocks excessive requests
3. Rate limit headers included in responses
4. Error codes documented at /api/v1/errors/codes
5. Retry-After header present for retryable errors

## Example Responses

### Error Response
```json
{
  "error": {
    "code": "VAL_FILE_TOO_LARGE",
    "message": "The uploaded file exceeds the maximum allowed size",
    "details": {
      "max_size_mb": 50,
      "actual_size_mb": 75
    },
    "retry_after": null
  }
}
```

### Rate Limited Response
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please slow down",
    "details": {},
    "retry_after": 60.0
  }
}
```

### Rate Limit Headers
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
Retry-After: 60
```

## Testing

```bash
# Test error codes endpoint
curl http://localhost:8000/api/v1/errors/codes

# Test rate limiting (make 61+ requests quickly)
for i in {1..65}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health; done
# Should see 200 for first 60, then 429
```