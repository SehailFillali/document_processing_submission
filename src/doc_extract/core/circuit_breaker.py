"""Circuit breaker pattern for external service calls."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from doc_extract.core.logging import logger


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 30.0
    half_open_max_calls: int = 3


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: float | None = None
    state_changes: list = field(default_factory=list)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit is open and requests are blocked."""

    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{circuit_name}' is open. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """Circuit breaker for external service calls."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()
        self.stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition."""
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time >= self.config.timeout_seconds
        ):
            return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            current_state = self.state
            self.stats.total_calls += 1

            if current_state == CircuitState.OPEN:
                self.stats.rejected_calls += 1
                retry_after = self.config.timeout_seconds - (
                    time.time() - self._last_failure_time
                )
                raise CircuitBreakerOpenError(self.name, max(0, retry_after))

            if current_state == CircuitState.HALF_OPEN:
                # Formally transition _state so success/failure handlers work correctly
                if self._state == CircuitState.OPEN:
                    self._transition_to(CircuitState.HALF_OPEN)
                if self._success_count >= self.config.half_open_max_calls:
                    self.stats.rejected_calls += 1
                    raise CircuitBreakerOpenError(self.name, 1.0)

        try:
            result = await func(*args, **kwargs)

            async with self._lock:
                self._failure_count = 0
                if self._state == CircuitState.HALF_OPEN:
                    self._success_count += 1
                    if self._success_count >= self.config.success_threshold:
                        self._transition_to(CircuitState.CLOSED)
                self.stats.successful_calls += 1

            return result

        except Exception:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                self.stats.failed_calls += 1
                self.stats.last_failure_time = self._last_failure_time

                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

            raise

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state with logging."""
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.OPEN:
            logger.warning(
                f"Circuit '{self.name}' opened after {self._failure_count} failures"
            )
        elif new_state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit '{self.name}' transitioning to half-open")
        elif new_state == CircuitState.CLOSED:
            logger.info(
                f"Circuit '{self.name}' closed after {self._success_count} successes"
            )

        self.stats.state_changes.append(
            {"timestamp": time.time(), "from": old_state.value, "to": new_state.value}
        )

        if new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def get_health_status(self) -> dict:
        """Get circuit health for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful": self.stats.successful_calls,
                "failed": self.stats.failed_calls,
                "rejected": self.stats.rejected_calls,
                "success_rate": (
                    self.stats.successful_calls / self.stats.total_calls
                    if self.stats.total_calls > 0
                    else 0
                ),
            },
        }

    async def reset(self) -> None:
        """Manually reset the circuit."""
        async with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0


class CircuitBreakerManager:
    """Manages multiple circuit breakers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self, name: str, config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get_all_health(self) -> dict:
        """Get health status of all circuits."""
        return {name: cb.get_health_status() for name, cb in self._breakers.items()}


circuit_breaker_manager = CircuitBreakerManager()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get circuit breaker for a service."""
    return circuit_breaker_manager.get_or_create(
        name,
        CircuitBreakerConfig(
            failure_threshold=5, success_threshold=3, timeout_seconds=30.0
        ),
    )
