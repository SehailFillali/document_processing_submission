"""Observability and cost monitoring endpoints."""

from datetime import UTC, datetime

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
    """Get cost statistics for the system."""
    from doc_extract.adapters.gemini_adapter import get_total_system_cost
    from doc_extract.api.main import db

    total_cost = get_total_system_cost()

    try:
        result = await db.query("submissions", page_size=1)
        submission_count = result.total_count
    except Exception:
        submission_count = 0

    avg_cost = total_cost / submission_count if submission_count > 0 else 0

    budget_status = obs_config.check_budget(total_cost)

    return CostStatsResponse(
        total_cost_usd=round(total_cost, 4),
        total_submissions=submission_count,
        average_cost_per_submission=round(avg_cost, 4),
        daily_budget_usd=obs_config.daily_budget_usd,
        budget_status=budget_status["status"],
        percent_used=budget_status["percent_used"],
    )


@router.get("/observability/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics():
    """Get comprehensive system metrics."""
    from doc_extract.adapters.gemini_adapter import get_total_system_cost
    from doc_extract.api.main import db

    total_cost = get_total_system_cost()

    try:
        result = await db.query("submissions", page_size=1)
        submission_count = result.total_count
    except Exception:
        submission_count = 0

    avg_cost = total_cost / submission_count if submission_count > 0 else 0
    budget_status = obs_config.check_budget(total_cost)

    circuits = None
    try:
        from doc_extract.core.circuit_breaker import circuit_breaker_manager

        circuits = circuit_breaker_manager.get_all_health()
    except Exception:
        pass

    return SystemMetricsResponse(
        timestamp=datetime.now(UTC).isoformat(),
        cost=CostStatsResponse(
            total_cost_usd=round(total_cost, 4),
            total_submissions=submission_count,
            average_cost_per_submission=round(avg_cost, 4),
            daily_budget_usd=obs_config.daily_budget_usd,
            budget_status=budget_status["status"],
            percent_used=budget_status["percent_used"],
        ),
        circuits=circuits,
    )


@router.post("/observability/cost/reset")
async def reset_cost_tracking():
    """Reset cost tracking."""
    from doc_extract.adapters.gemini_adapter import _cost_tracker

    _cost_tracker.clear()
    return {"message": "Cost tracking reset"}
