"""Tests for observability, cost tracking, and budget checking."""

import pytest

from doc_extract.core.observability import ObservabilityConfig, obs_context


class TestCostCalculation:
    """Test LLM cost calculation."""

    def test_calculate_cost_known_values(self):
        """Known token counts produce correct cost."""
        config = ObservabilityConfig()
        # 1M input tokens at $0.075, 1M output tokens at $0.30
        cost = config.calculate_cost(1_000_000, 1_000_000)
        assert cost == pytest.approx(0.375)

    def test_calculate_cost_zero_tokens(self):
        """Zero tokens produce zero cost."""
        config = ObservabilityConfig()
        assert config.calculate_cost(0, 0) == 0.0

    def test_calculate_cost_small_request(self):
        """Small request cost is proportional."""
        config = ObservabilityConfig()
        # 1000 input, 500 output
        cost = config.calculate_cost(1000, 500)
        expected = (1000 / 1_000_000) * 0.075 + (500 / 1_000_000) * 0.30
        assert cost == pytest.approx(expected)


class TestBudgetChecking:
    """Test budget threshold checks."""

    def test_check_budget_ok(self):
        """Under budget returns ok."""
        config = ObservabilityConfig()
        config.daily_budget_usd = 100.0
        config.warn_threshold_percent = 80.0

        result = config.check_budget(10.0)
        assert result["status"] == "ok"
        assert result["percent_used"] == 10.0

    def test_check_budget_warning(self):
        """Over warning threshold returns warning."""
        config = ObservabilityConfig()
        config.daily_budget_usd = 100.0
        config.warn_threshold_percent = 80.0

        result = config.check_budget(85.0)
        assert result["status"] == "warning"
        assert result["percent_used"] == 85.0

    def test_check_budget_exceeded(self):
        """Over budget returns exceeded."""
        config = ObservabilityConfig()
        config.daily_budget_usd = 100.0

        result = config.check_budget(150.0)
        assert result["status"] == "exceeded"
        assert result["current_cost_usd"] == 150.0


class TestObsContext:
    """Test observability context manager."""

    @pytest.mark.asyncio
    async def test_obs_context_disabled(self):
        """Context manager is a no-op when disabled."""
        async with obs_context("test_op", foo="bar"):
            result = 42
        assert result == 42

    @pytest.mark.asyncio
    async def test_obs_context_propagates_exception(self):
        """Exceptions propagate through context."""
        with pytest.raises(ValueError, match="test error"):
            async with obs_context("failing_op"):
                raise ValueError("test error")


class TestObservabilityEndpoints:
    """Test observability API endpoints."""

    def _mock_db(self):
        """Create a mock SQLiteAdapter."""
        from unittest.mock import AsyncMock, MagicMock

        mock = MagicMock()
        mock.init_tables = AsyncMock()
        mock.query = AsyncMock(
            return_value=MagicMock(items=[], total_count=0, page=1, page_size=20)
        )
        return mock

    def test_cost_endpoint(self):
        """Cost endpoint returns valid data."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        with patch("doc_extract.api.main.db", self._mock_db()):
            client = TestClient(app)
            r = client.get("/api/v1/observability/cost")
        assert r.status_code == 200

        data = r.json()
        assert "total_cost_usd" in data
        assert "daily_budget_usd" in data
        assert "budget_status" in data
        assert data["budget_status"] in ("ok", "warning", "exceeded")

    def test_metrics_endpoint(self):
        """Metrics endpoint returns valid data."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        with patch("doc_extract.api.main.db", self._mock_db()):
            client = TestClient(app)
            r = client.get("/api/v1/observability/metrics")
        assert r.status_code == 200

        data = r.json()
        assert "timestamp" in data
        assert "cost" in data

    def test_cost_reset_endpoint(self):
        """Cost reset endpoint works."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        with patch("doc_extract.api.main.db", self._mock_db()):
            client = TestClient(app)
            r = client.post("/api/v1/observability/cost/reset")
        assert r.status_code == 200
