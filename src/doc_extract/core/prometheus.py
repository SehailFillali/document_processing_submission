"""Prometheus metrics for the document extraction system.

Inspired by ~/projects/llm-service/src/llm_service/core/metrics.py.
Provides request-level and business-level metrics.

ADR Reference: docs/adr/017_logfire_observability.md
"""

import time
from collections.abc import Callable

from fastapi import APIRouter, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# --- Request Metrics ---

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Time spent processing HTTP requests",
    ["method", "path", "status_code"],
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"],
)

# --- Business Metrics ---

EXTRACTION_REQUESTS = Counter(
    "extraction_requests_total",
    "Total extraction requests",
    ["status"],  # success, failed, partial
)

EXTRACTION_DURATION = Histogram(
    "extraction_duration_seconds",
    "Time spent on document extraction",
    ["document_type"],
    buckets=[1, 5, 10, 15, 30, 60, 120],
)

LLM_API_CALLS = Counter(
    "llm_api_calls_total",
    "Total LLM API calls",
    ["model", "status"],  # success, error, timeout
)

LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["model", "type"],  # prompt, completion
)

VALIDATION_FAILURES = Counter(
    "validation_failures_total",
    "Total validation failures by rule",
    ["rule_id"],
)

QA_SCORE = Histogram(
    "qa_score",
    "Distribution of QA scores from critique agent",
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

RETRY_COUNT = Counter(
    "self_correction_retries_total",
    "Total self-correction retry attempts",
)

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["circuit_name"],
)

ACTIVE_SUBMISSIONS = Gauge(
    "active_submissions",
    "Number of currently processing submissions",
)


# --- Middleware ---


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics automatically."""

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = request.url.path
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.perf_counter() - start_time
            REQUEST_DURATION.labels(
                method=method, path=path, status_code=status_code
            ).observe(duration)
            REQUEST_COUNT.labels(
                method=method, path=path, status_code=status_code
            ).inc()


# --- Metrics Endpoint ---

metrics_router = APIRouter()


@metrics_router.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
