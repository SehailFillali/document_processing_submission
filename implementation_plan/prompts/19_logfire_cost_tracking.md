# Prompt 19: Logfire Observability & Cost Tracking

## Status
[COMPLETED]

## Context

We need production-grade observability with OpenTelemetry/Logfire integration to track costs, performance, and help debug issues. This demonstrates "Head of Engineering" thinking about operational excellence.

## Objective

Add Logfire/OpenTelemetry instrumentation to:
1. Trace requests end-to-end
2. Track LLM token usage and costs
3. Create a cost dashboard endpoint
4. Add custom spans for business logic

## Requirements

### 1. Create Observability Configuration

File: `src/doc_extract/core/observability.py`

```python
"""Observability configuration with Logfire/OpenTelemetry."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from doc_extract.core.logging import logger

# Try to import logfire - make it optional
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
        
        # Token pricing (per 1M tokens)
        # Gemini 2.0 Flash pricing
        self.gemini_input_cost_per_million = 0.075  # $0.075 per 1M input
        self.gemini_output_cost_per_million = 0.30  # $0.30 per 1M output
        
        # Budget limits
        self.daily_budget_usd = float(os.getenv("DAILY_BUDGET_USD", "100.0"))
        self.warn_threshold_percent = float(os.getenv("WARN_THRESHOLD_PERCENT", "80.0"))
    
    def initialize_logfire(self) -> None:
        """Initialize Logfire with instrumentor."""
        if not LOGFIRE_AVAILABLE or not self.enabled:
            return
        
        try:
            # Configure Logfire
            logfire.configure(
                service_name=self.service_name,
                environment=self.environment,
                # Use OTLP endpoint if configured
                otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
                sampling_rate=os.getenv("LOGFIRE_SAMPLE_RATE", "1.0"),
            )
            
            # Instrument FastAPI
            logfire.instrument_fastapi()
            
            # Instrument HTTPX (for LLM calls)
            logfire.instrument_httpx()
            
            # Instrument asyncio
            logfire.instrument_asyncio()
            
            logger.info("Logfire initialized successfully")
            
        except Exception as e:
            logger.warning(f"Failed to initialize Logfire: {e}")
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for LLM call.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.gemini_input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * self.gemini_output_cost_per_million
        return input_cost + output_cost
    
    def check_budget(self, current_cost: float) -> dict:
        """Check if current cost exceeds budget thresholds.
        
        Returns:
            Dict with budget status
        """
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
            "warn_threshold_percent": self.warn_threshold_percent
        }


# Global config instance
obs_config = ObservabilityConfig()


@asynccontextmanager
async def obs_context(
    operation_name: str,
    **attributes
) -> AsyncGenerator[None, None]:
    """Context manager for observability spans.
    
    Usage:
        async with obs_context("extract_document", submission_id="123"):
            # Do work
            pass
    """
    if not LOGFIRE_AVAILABLE or not obs_config.enabled:
        yield
        return
    
    with logfire.span(operation_name, **attributes):
        try:
            yield
        except Exception as e:
            logfire.error(f"Error in {operation_name}: {e}")
            raise
```

### 2. Update LLM Adapter with Cost Tracking

File: `src/doc_extract/adapters/gemini_adapter.py` (add cost tracking)

```python
"""Gemini LLM adapter with observability and cost tracking."""
import os
import time
from typing import Type
from pydantic import BaseModel

from pydantic_ai import Agent, DocumentUrl
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from doc_extract.ports.llm import (
    LLMPort, ExtractionRequest, ExtractionResponse, LLMError
)
from doc_extract.core.logging import logger
from doc_extract.core.circuit_breaker import get_circuit_breaker
from doc_extract.core.observability import obs_context, obs_config


# Try to import logfire for instrumentation
try:
    import logfire
    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False


class GeminiAdapter(LLMPort):
    """Gemini API implementation with observability."""
    
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY required")
        
        self.provider = GoogleProvider(api_key=self.api_key)
        self.model = GoogleModel(model_name, provider=self.provider)
        self._circuit_breaker = get_circuit_breaker("gemini")
        
        # Cost tracking
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        
        logger.info(f"Initialized GeminiAdapter with model {model_name}")
    
    async def extract_structured(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract with observability and cost tracking."""
        start_time = time.time()
        
        # Use logfire span if available
        if LOGFIRE_AVAILABLE and obs_config.enabled:
            with logfire.span(
                "llm_extraction",
                document_type=request.document_type,
                model=self.model_name
            ) as span:
                try:
                    result = await self._do_extraction(request)
                    
                    # Calculate and track cost
                    input_tokens = getattr(result, 'input_tokens', 0)
                    output_tokens = getattr(result, 'output_tokens', 0)
                    cost = obs_config.calculate_cost(input_tokens, output_tokens)
                    self._total_cost_usd += cost
                    self._total_tokens += input_tokens + output_tokens
                    
                    # Add to span
                    span.set_attribute("input_tokens", input_tokens)
                    span.set_attribute("output_tokens", output_tokens)
                    span.set_attribute("cost_usd", cost)
                    
                    return result
                    
                except Exception as e:
                    span.set_attribute("error", str(e))
                    raise
        else:
            # No observability - just call directly
            return await self._do_extraction(request)
    
    async def _do_extraction(self, request: ExtractionRequest) -> ExtractionResponse:
        """Actual extraction logic."""
        # ... existing implementation ...
        pass
    
    def get_cost_stats(self) -> dict:
        """Get cost statistics for this adapter."""
        budget_status = obs_config.check_budget(self._total_cost_usd)
        
        return {
            "total_cost_usd": round(self._total_cost_usd, 4),
            "total_tokens": self._total_tokens,
            "budget": budget_status
        }
    
    def reset_cost_tracking(self) -> None:
        """Reset cost counters (e.g., for daily reset)."""
        self._total_cost_usd = 0.0
        self._total_tokens = 0


# Global adapter instance with cost tracking
_cost_tracker: dict[str, float] = {}  # submission_id -> cost


def track_extraction_cost(submission_id: str, cost: float) -> None:
    """Track extraction cost for a submission."""
    _cost_tracker[submission_id] = _cost_tracker.get(submission_id, 0) + cost


def get_submission_cost(submission_id: str) -> float:
    """Get total cost for a submission."""
    return _cost_tracker.get(submission_id, 0)


def get_total_system_cost() -> float:
    """Get total system cost."""
    return sum(_cost_tracker.values())
```

### 3. Create Cost Dashboard Endpoint

File: `src/doc_extract/api/observability_endpoints.py`

```python
"""Observability and cost monitoring endpoints."""
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

from doc_extract.core.observability import obs_config

router = APIRouter(prefix="/api/v1", tags=["Observability"])


class CostStatsResponse(BaseModel):
    """Cost statistics response."""
    total_cost_usd: float
    total_submissions: int
    average_cost_per_submission: float
    daily_budget_usd: float
    budget_status: str
    percent_used: float


class SystemMetricsResponse(BaseModel):
    """System metrics response."""
    timestamp: str
    cost: CostStatsResponse
    circuits: dict | None = None


@router.get("/observability/cost", response_model=CostStatsResponse)
async def get_cost_stats():
    """Get cost statistics for the system.
    
    Returns:
        Current cost, budget status, and per-submission averages
    """
    from doc_extract.adapters.gemini_adapter import get_total_system_cost
    from doc_extract.api.main import submissions_db
    
    total_cost = get_total_system_cost()
    submission_count = len(submissions_db)
    avg_cost = total_cost / submission_count if submission_count > 0 else 0
    
    budget_status = obs_config.check_budget(total_cost)
    
    return CostStatsResponse(
        total_cost_usd=round(total_cost, 4),
        total_submissions=submission_count,
        average_cost_per_submission=round(avg_cost, 4),
        daily_budget_usd=obs_config.daily_budget_usd,
        budget_status=budget_status["status"],
        percent_used=budget_status["percent_used"]
    )


@router.get("/observability/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics():
    """Get comprehensive system metrics.
    
    Includes cost, circuit breaker status, and system health.
    """
    from doc_extract.adapters.gemini_adapter import get_total_system_cost
    from doc_extract.api.main import submissions_db
    from doc_extract.core.circuit_breaker import circuit_breaker_manager
    
    total_cost = get_total_system_cost()
    submission_count = len(submissions_db)
    avg_cost = total_cost / submission_count if submission_count > 0 else 0
    budget_status = obs_config.check_budget(total_cost)
    
    return SystemMetricsResponse(
        timestamp=datetime.utcnow().isoformat(),
        cost=CostStatsResponse(
            total_cost_usd=round(total_cost, 4),
            total_submissions=submission_count,
            average_cost_per_submission=round(avg_cost, 4),
            daily_budget_usd=obs_config.daily_budget_usd,
            budget_status=budget_status["status"],
            percent_used=budget_status["percent_used"]
        ),
        circuits=circuit_breaker_manager.get_all_health()
    )


@router.post("/observability/cost/reset")
async def reset_cost_tracking():
    """Reset cost tracking (e.g., for new billing cycle)."""
    # This would need to be implemented in the adapter
    return {"message": "Cost tracking reset"}
```

### 4. Update API Main

File: `src/doc_extract/api/main.py`

```python
# Add imports
from doc_extract.core.observability import obs_config, obs_context
from doc_extract.api.observability_endpoints import router as obs_router

# Initialize observability on startup
@app.on_event("startup")
async def startup():
    obs_config.initialize_logfire()
    # ... existing startup code

# Include observability router
app.include_router(obs_router)
```

### 5. Update .env.example

```bash
# Observability
OBSERVABILITY_ENABLED=false
SERVICE_NAME=doc-extract
ENVIRONMENT=local
LOGFIRE_SAMPLE_RATE=1.0
# OTLP_ENDPOINT=https://your-otlp-collector:4318

# Cost Tracking
DAILY_BUDGET_USD=100.0
WARN_THRESHOLD_PERCENT=80.0
```

### 6. Update pyproject.toml

```toml
dependencies = [
    # ... existing ...
    "logfire[fastapi,httpx,pydantic]>=3.14.0",
]
```

## Deliverables

- [ ] src/doc_extract/core/observability.py - Observability config and context
- [ ] src/doc_extract/adapters/gemini_adapter.py - Updated with cost tracking
- [ ] src/doc_extract/api/observability_endpoints.py - Cost/metrics endpoints
- [ ] src/doc_extract/api/main.py - Initialize and include router
- [ ] .env.example - Add observability variables
- [ ] pyproject.toml - Add logfire dependency

## Success Criteria

1. Token usage tracked for each extraction
2. Cost calculated and accumulated
3. Budget status endpoint works
4. Logfire traces spans when enabled
5. No performance impact when disabled

## Endpoints

| Endpoint | Description |
| -------- | ----------- |
| GET /api/v1/observability/cost | Cost statistics and budget status |
| GET /api/v1/observability/metrics | Full system metrics with circuits |

## Testing

```bash
# Test cost endpoint
curl http://localhost:8000/api/v1/observability/cost

# Response:
# {
#   "total_cost_usd": 0.0234,
#   "total_submissions": 10,
#   "average_cost_per_submission": 0.0023,
#   "daily_budget_usd": 100.0,
#   "budget_status": "ok",
#   "percent_used": 0.0
# }
```
