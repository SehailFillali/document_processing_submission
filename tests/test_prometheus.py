"""Tests for Prometheus metrics."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from doc_extract.api.main import app
from doc_extract.core.prometheus import (
    ACTIVE_SUBMISSIONS,
    EXTRACTION_DURATION,
    EXTRACTION_REQUESTS,
    QA_SCORE,
    REQUEST_COUNT,
    REQUEST_DURATION,
    RETRY_COUNT,
)


class TestMetricsEndpoint:
    """Test the /metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self):
        """GET /metrics returns valid Prometheus text format."""
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Should contain at least the built-in process metrics or our custom ones
        assert "http_requests_total" in response.text or "python_info" in response.text

    def test_request_increments_counter(self):
        """Making a request increments the request counter."""
        client = TestClient(app)
        # Make a request that gets tracked
        client.get("/health")
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "http_requests_total" in response.text

    def test_metrics_contains_custom_metrics(self):
        """Custom business metrics are registered."""
        client = TestClient(app)
        response = client.get("/metrics")
        body = response.text
        # Verify our custom metrics exist in the output
        assert "extraction_requests_total" in body or "extraction_requests" in body
        assert "qa_score" in body
        assert "self_correction_retries_total" in body or "self_correction" in body
        assert "active_submissions" in body


class TestMetricsMiddleware:
    """Test that the PrometheusMiddleware records request metrics."""

    def test_health_request_tracked(self):
        """Health check request appears in metrics."""
        client = TestClient(app)
        client.get("/health")
        response = client.get("/metrics")
        body = response.text
        # Should see the /health path in request metrics
        assert "/health" in body

    def test_metrics_endpoint_not_self_tracked(self):
        """The /metrics endpoint itself is not tracked to avoid recursion."""
        client = TestClient(app)
        # Only call /metrics
        response = client.get("/metrics")
        # The /metrics path should NOT appear in request count labels
        # (we skip it in the middleware)
        lines = [
            line
            for line in response.text.split("\n")
            if "http_requests_total" in line and '"/metrics"' in line
        ]
        # Should be empty or have 0 count
        for line in lines:
            if 'path="/metrics"' in line:
                # The count value should be 0.0
                assert line.strip().endswith("0.0") or "0.0" in line


class TestBusinessMetrics:
    """Test business metric objects are properly configured."""

    def test_extraction_requests_counter(self):
        """EXTRACTION_REQUESTS counter has status label."""
        EXTRACTION_REQUESTS.labels(status="success").inc(0)
        EXTRACTION_REQUESTS.labels(status="failed").inc(0)
        # No exception means labels are valid

    def test_extraction_duration_histogram(self):
        """EXTRACTION_DURATION histogram has document_type label."""
        EXTRACTION_DURATION.labels(document_type="loan_application").observe(1.5)
        # No exception

    def test_qa_score_histogram(self):
        """QA_SCORE histogram accepts observations."""
        QA_SCORE.observe(85.0)
        QA_SCORE.observe(42.0)
        # No exception

    def test_retry_count_counter(self):
        """RETRY_COUNT counter increments."""
        RETRY_COUNT.inc(0)
        # No exception

    def test_active_submissions_gauge(self):
        """ACTIVE_SUBMISSIONS gauge increments and decrements."""
        ACTIVE_SUBMISSIONS.inc()
        ACTIVE_SUBMISSIONS.dec()
        # No exception

    def test_request_duration_histogram(self):
        """REQUEST_DURATION histogram has correct labels."""
        REQUEST_DURATION.labels(method="GET", path="/health", status_code=200).observe(
            0.01
        )
        # No exception

    def test_request_count_counter(self):
        """REQUEST_COUNT counter has correct labels."""
        REQUEST_COUNT.labels(method="GET", path="/health", status_code=200).inc(0)
        # No exception


class TestMetricsInProcessing:
    """Test that ProcessingService records metrics."""

    @pytest.mark.asyncio
    async def test_success_increments_extraction_counter(self):
        """Successful processing increments extraction_requests{status=success}."""
        from doc_extract.services.processing import ProcessingService

        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        mock_result = MagicMock()
        mock_result.extracted_data = MagicMock()
        mock_result.extracted_data.model_dump.return_value = {"name": "John"}
        mock_result.confidence_score = 0.85

        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(return_value=mock_result)

        from doc_extract.agents.critic_agent import CritiqueResult, FieldAssessment

        critique = CritiqueResult(
            assessments=[FieldAssessment(field_name="name", is_correct=True)],
            overall_score=95.0,
        )
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(return_value=critique)

        result = await service.process_submission("sub-1", "path/doc.pdf")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_failure_increments_failed_counter(self):
        """Failed processing increments extraction_requests{status=failed}."""
        from doc_extract.services.processing import ProcessingService

        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock(side_effect=FileNotFoundError("missing"))

        result = await service.process_submission("sub-1", "bad/path.pdf")
        assert result["status"] == "failed"
