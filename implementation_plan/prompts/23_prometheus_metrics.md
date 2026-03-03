# Prompt 23: Prometheus Metrics

## Status
[COMPLETED]

## Context

The reference implementation (`~/projects/llm-service`) uses `prometheus_client` with a `RequestMetricsMiddleware` for automatic request duration and throughput tracking, plus custom counters for validation failures and LLM errors. We need similar production-grade metrics.

## Objective

Add Prometheus metrics with a `/metrics` endpoint and request middleware.

## Requirements

### 1. Add Dependency

In `pyproject.toml`, add:
```toml
"prometheus-client>=0.20.0",
```

### 2. Create Metrics Module

File: `src/doc_extract/core/prometheus.py`

```python
"""Prometheus metrics for the document extraction system.

Inspired by ~/projects/llm-service/src/llm_service/core/metrics.py.
Provides request-level and business-level metrics.

ADR Reference: docs/adr/017_logfire_observability.md
"""
import time
from collections.abc import Callable

from fastapi import Request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import APIRouter


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
```

### 3. Wire Into Application

In `src/doc_extract/api/main.py`, add:

```python
from doc_extract.core.prometheus import PrometheusMiddleware, metrics_router

app.add_middleware(PrometheusMiddleware)
app.include_router(metrics_router)
```

### 4. Instrument Processing Service

In `src/doc_extract/services/processing.py`, add metric recording at key points:

```python
from doc_extract.core.prometheus import (
    EXTRACTION_REQUESTS,
    EXTRACTION_DURATION,
    LLM_TOKENS,
    QA_SCORE,
    RETRY_COUNT,
    ACTIVE_SUBMISSIONS,
)

# At start of process_submission:
ACTIVE_SUBMISSIONS.inc()

# After LLM call:
LLM_TOKENS.labels(model="gpt-4o-mini", type="prompt").inc(token_usage["prompt_tokens"])
LLM_TOKENS.labels(model="gpt-4o-mini", type="completion").inc(token_usage["completion_tokens"])

# After critique:
QA_SCORE.observe(qa_score)

# On retry:
RETRY_COUNT.inc()

# At end (in finally block):
EXTRACTION_REQUESTS.labels(status="success").inc()
EXTRACTION_DURATION.labels(document_type="loan_application").observe(pipeline_time)
ACTIVE_SUBMISSIONS.dec()
```

### 5. Metrics to Track

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_request_duration_seconds` | Histogram | method, path, status_code | Request latency |
| `http_requests_total` | Counter | method, path, status_code | Request throughput |
| `extraction_requests_total` | Counter | status | Extraction outcomes |
| `extraction_duration_seconds` | Histogram | document_type | Extraction latency |
| `llm_api_calls_total` | Counter | model, status | LLM call outcomes |
| `llm_tokens_total` | Counter | model, type | Token usage |
| `validation_failures_total` | Counter | rule_id | Validation errors |
| `qa_score` | Histogram | - | QA score distribution |
| `self_correction_retries_total` | Counter | - | Retry count |
| `circuit_breaker_state` | Gauge | circuit_name | CB state |
| `active_submissions` | Gauge | - | In-flight work |

### 6. Add Test

File: `tests/test_prometheus.py`

```python
"""Tests for Prometheus metrics."""
import pytest
from fastapi.testclient import TestClient
from doc_extract.api.main import app


def test_metrics_endpoint_returns_prometheus_format():
    """Test /metrics returns valid Prometheus format."""
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text


def test_request_increments_counter():
    """Test that making a request increments the counter."""
    client = TestClient(app)
    client.get("/health")
    response = client.get("/metrics")
    assert "http_requests_total" in response.text
```

## Verification

```bash
# All tests must pass
just test

# Verify metrics endpoint
just dev
curl http://localhost:8000/metrics | grep extraction
```

## Constraints
- **NO REGRESSION** — All existing tests must pass
- **Low overhead** — Metrics collection must not add measurable latency
- **Standard format** — Must be scrapable by Prometheus
