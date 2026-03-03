"""Rate limiting middleware using token bucket algorithm."""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request
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
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key}"

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0]}"

        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _cleanup_old_requests(self, stats: RateLimitStats, current_time: float) -> None:
        """Remove requests outside the time windows."""
        stats.minute_requests = [
            t for t in stats.minute_requests if current_time - t < 60
        ]

        stats.hour_requests = [
            t for t in stats.hour_requests if current_time - t < 3600
        ]

    async def check_rate_limit(self, request: Request) -> None:
        """Check if request is within rate limits."""
        client_id = self._get_client_id(request)
        current_time = time.time()

        stats = self._clients[client_id]
        self._cleanup_old_requests(stats, current_time)

        if len(stats.minute_requests) >= self.config.requests_per_minute:
            logger.warning(f"Rate limit exceeded (per-minute) for {client_id}")
            raise RateLimitError(
                message=f"Rate limit: {self.config.requests_per_minute} requests per minute",
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                retry_after=60.0,
            )

        if len(stats.hour_requests) >= self.config.requests_per_hour:
            logger.warning(f"Rate limit exceeded (per-hour) for {client_id}")
            raise RateLimitError(
                message=f"Rate limit: {self.config.requests_per_hour} requests per hour",
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                retry_after=3600.0,
            )

        day_requests = sum(1 for t in stats.hour_requests if current_time - t < 86400)
        if day_requests >= self.config.requests_per_day:
            logger.warning(f"Rate limit exceeded (per-day) for {client_id}")
            raise RateLimitError(
                message=f"Daily limit: {self.config.requests_per_day} requests per day",
                error_code=ErrorCode.RATE_DAILY_QUOTA_EXCEEDED,
                retry_after=86400.0,
            )

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
            "reset_in_seconds": 60 - (current_time % 60),
        }


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting."""

    async def dispatch(self, request: Request, call_next: Callable):
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
                headers={"Retry-After": str(e.retry_after)} if e.retry_after else {},
            )

        response = await call_next(request)

        quota = rate_limiter.get_remaining_quota(request)
        response.headers["X-RateLimit-Limit"] = str(
            rate_limiter.config.requests_per_minute
        )
        response.headers["X-RateLimit-Remaining"] = str(
            quota["requests_per_minute_remaining"]
        )

        return response
