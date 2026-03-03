"""Observability configuration with Logfire/OpenTelemetry."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from doc_extract.core.logging import logger

try:
    import logfire

    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False
    logger.warning("logfire not installed. Run: uv add logfire")


class ObservabilityConfig:
    """Configuration for observability."""

    def __init__(self):
        self.enabled = os.getenv("OBSERVABILITY_ENABLED", "false").lower() == "true"
        self.service_name = os.getenv("SERVICE_NAME", "doc-extract")
        self.environment = os.getenv("ENVIRONMENT", "local")

        self.gemini_input_cost_per_million = 0.075
        self.gemini_output_cost_per_million = 0.30

        self.daily_budget_usd = float(os.getenv("DAILY_BUDGET_USD", "100.0"))
        self.warn_threshold_percent = float(os.getenv("WARN_THRESHOLD_PERCENT", "80.0"))

    def initialize_logfire(self) -> None:
        """Initialize Logfire with instrumentor."""
        if not LOGFIRE_AVAILABLE or not self.enabled:
            return

        try:
            logfire.configure(
                service_name=self.service_name,
                environment=self.environment,
                otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
                sampling_rate=os.getenv("LOGFIRE_SAMPLE_RATE", "1.0"),
            )

            logfire.instrument_fastapi()
            logfire.instrument_httpx()
            logfire.instrument_asyncio()

            logger.info("Logfire initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize Logfire: {e}")

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for LLM call."""
        input_cost = (input_tokens / 1_000_000) * self.gemini_input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * self.gemini_output_cost_per_million
        return input_cost + output_cost

    def check_budget(self, current_cost: float) -> dict:
        """Check if current cost exceeds budget thresholds."""
        percent_used = (current_cost / self.daily_budget_usd) * 100

        status = "ok"
        if percent_used >= self.warn_threshold_percent:
            status = "warning"
        if current_cost >= self.daily_budget_usd:
            status = "exceeded"

        return {
            "status": status,
            "current_cost_usd": round(current_cost, 4),
            "daily_budget_usd": self.daily_budget_usd,
            "percent_used": round(percent_used, 1),
            "warn_threshold_percent": self.warn_threshold_percent,
        }


obs_config = ObservabilityConfig()


@asynccontextmanager
async def obs_context(operation_name: str, **attributes) -> AsyncGenerator[None, None]:
    """Context manager for observability spans."""
    if not LOGFIRE_AVAILABLE or not obs_config.enabled:
        yield
        return

    with logfire.span(operation_name, **attributes):
        try:
            yield
        except Exception as e:
            logfire.error(f"Error in {operation_name}: {e}")
            raise
