"""Tests for circuit breaker state machine."""

import asyncio

import pytest

from doc_extract.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitState,
    get_circuit_breaker,
)


@pytest.fixture
def cb():
    """Create a circuit breaker with low thresholds for testing."""
    return CircuitBreaker(
        "test",
        CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=0.1,
            half_open_max_calls=2,
        ),
    )


async def _success():
    return "ok"


async def _failure():
    raise RuntimeError("boom")


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_closed_allows_calls(self, cb):
        """Normal calls pass through when circuit is closed."""
        result = await cb.call(_success)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self, cb):
        """Circuit opens after N consecutive failures."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        assert cb._state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_when_open(self, cb):
        """Requests are rejected when circuit is open."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await cb.call(_success)

        assert exc_info.value.circuit_name == "test"
        assert exc_info.value.retry_after >= 0

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, cb):
        """Circuit transitions to half-open after timeout."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        assert cb._state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # State property should report HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self, cb):
        """Circuit closes after M successes in half-open."""
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        await asyncio.sleep(0.15)

        # Successful calls in half-open should close circuit
        await cb.call(_success)
        await cb.call(_success)

        assert cb._state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens(self, cb):
        """Failure in half-open re-opens the circuit."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        await asyncio.sleep(0.15)

        # Fail again in half-open
        with pytest.raises(RuntimeError):
            await cb.call(_failure)

        # Should still count failures


class TestCircuitBreakerStats:
    """Test stats tracking."""

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cb):
        """Stats counters are accurate."""
        await cb.call(_success)
        await cb.call(_success)

        with pytest.raises(RuntimeError):
            await cb.call(_failure)

        assert cb.stats.total_calls == 3
        assert cb.stats.successful_calls == 2
        assert cb.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_rejected_calls_tracked(self, cb):
        """Rejected calls are counted."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_success)

        assert cb.stats.rejected_calls == 1

    @pytest.mark.asyncio
    async def test_health_status(self, cb):
        """Health status returns correct data."""
        await cb.call(_success)

        health = cb.get_health_status()
        assert health["name"] == "test"
        assert health["state"] == "closed"
        assert health["stats"]["total_calls"] == 1
        assert health["stats"]["successful"] == 1
        assert health["stats"]["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_health_status_zero_calls(self, cb):
        """Health status handles zero calls."""
        health = cb.get_health_status()
        assert health["stats"]["success_rate"] == 0


class TestCircuitBreakerReset:
    """Test manual reset."""

    @pytest.mark.asyncio
    async def test_reset(self, cb):
        """Manual reset closes circuit."""
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_failure)

        assert cb._state == CircuitState.OPEN

        await cb.reset()
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0


class TestCircuitBreakerManager:
    """Test manager."""

    def test_get_or_create(self):
        """Manager creates and reuses breakers."""
        mgr = CircuitBreakerManager()
        cb1 = mgr.get_or_create("svc1")
        cb2 = mgr.get_or_create("svc1")
        cb3 = mgr.get_or_create("svc2")

        assert cb1 is cb2
        assert cb1 is not cb3

    def test_get_all_health(self):
        """Manager returns health for all breakers."""
        mgr = CircuitBreakerManager()
        mgr.get_or_create("a")
        mgr.get_or_create("b")

        health = mgr.get_all_health()
        assert "a" in health
        assert "b" in health
        assert health["a"]["name"] == "a"

    def test_get_circuit_breaker_helper(self):
        """Helper function returns a circuit breaker."""
        cb = get_circuit_breaker("test-helper")
        assert cb.name == "test-helper"
        assert cb.config.failure_threshold == 5
