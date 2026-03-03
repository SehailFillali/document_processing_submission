"""Resilience and monitoring endpoints."""

import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from doc_extract.core.circuit_breaker import circuit_breaker_manager

router = APIRouter(prefix="/api/v1", tags=["Resilience"])


class CircuitHealthResponse(BaseModel):
    """Response with circuit breaker health status."""

    circuits: dict
    timestamp: str


@router.get("/resilience/circuits", response_model=CircuitHealthResponse)
async def get_circuit_health():
    """Get health status of all circuit breakers."""
    return CircuitHealthResponse(
        circuits=circuit_breaker_manager.get_all_health(),
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
    )


@router.post("/resilience/circuits/{circuit_name}/reset")
async def reset_circuit(circuit_name: str):
    """Manually reset a circuit breaker."""
    cb = circuit_breaker_manager.get_or_create(circuit_name)
    await cb.reset()

    return {"message": f"Circuit '{circuit_name}' has been reset"}


@router.get("/resilience/status")
async def get_resilience_status():
    """Get overall system resilience status."""
    return {
        "circuit_breakers": len(circuit_breaker_manager._breakers),
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
