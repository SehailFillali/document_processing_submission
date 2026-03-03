# Prompt 18: Circuit Breaker & Resilience Patterns

## Status
[COMPLETED]

## Context

We need to add production-grade resilience patterns to handle LLM failures gracefully and prevent cascade failures when external services are unavailable.

## Objective

Implement a Circuit Breaker pattern for LLM calls and add resilience patterns that demonstrate "Head of Engineering" thinking.

## Requirements

### 1. Create Circuit Breaker Implementation

File: `src/doc_extract/core/circuit_breaker.py`

```python
"""Circuit breaker pattern for external service calls.

Implements the circuit breaker pattern to prevent cascade failures
when external services (LLM, storage, etc.) are unavailable.
"""
import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any

from doc_extract.core.logging import logger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"         # Failure threshold reached, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening circuit
    success_threshold: int = 3          # Successes in half-open to close
    timeout_seconds: float = 30.0       # Time before attempting recovery
    half_open_max_calls: int = 3       # Max calls in half-open state


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: float | None = None
    state_changes: list = field(default_factory=list)


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open and requests are blocked."""
    
    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{circuit_name}' is open. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """Circuit breaker for external service calls.
    
    Usage:
        cb = CircuitBreaker("gemini", CircuitBreakerConfig(
            failure_threshold=5,
            timeout_seconds=30
        ))
        
        try:
            result = await cb.call(llm.extract_structured, request)
        except CircuitBreakerOpen:
            # Handle circuit open - return fallback
            return get_fallback_response()
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None
    ):
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
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                # Transition to half-open after timeout
                return CircuitState.HALF_OPEN
        return self._state
    
    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args, **kwargs: Arguments to pass to function
            
        Returns:
            Result from function call
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        async with self._lock:
            current_state = self.state
            self.stats.total_calls += 1
            
            # Check if circuit is open
            if current_state == CircuitState.OPEN:
                self.stats.rejected_calls += 1
                retry_after = self.config.timeout_seconds - (time.time() - self._last_failure_time)
                raise CircuitBreakerOpen(self.name, max(0, retry_after))
            
            # In half-open, limit concurrent calls
            if current_state == CircuitState.HALF_OPEN:
                if self._success_count >= self.config.half_open_max_calls:
                    self.stats.rejected_calls += 1
                    raise CircuitBreakerOpen(self.name, 1.0)
        
        # Execute the function
        try:
            result = await func(*args, **kwargs)
            
            # Handle success
            async with self._lock:
                self._failure_count = 0
                if self._state == CircuitState.HALF_OPEN:
                    self._success_count += 1
                    if self._success_count >= self.config.success_threshold:
                        self._transition_to(CircuitState.CLOSED)
                self.stats.successful_calls += 1
            
            return result
            
        except Exception as e:
            # Handle failure
            async with self.lock if hasattr(self, 'lock') else self._lock:
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
        
        self.stats.state_changes.append({
            "timestamp": time.time(),
            "from": old_state.value,
            "to": new_state.value
        })
        
        # Reset counters
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
                    if self.stats.total_calls > 0 else 0
                )
            }
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
        self,
        name: str,
        config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]
    
    def get_all_health(self) -> dict:
        """Get health status of all circuits."""
        return {
            name: cb.get_health_status()
            for name, cb in self._breakers.items()
        }


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get circuit breaker for a service."""
    return circuit_breaker_manager.get_or_create(
        name,
        CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30.0
        )
    )
```

### 2. Update LLM Adapter with Circuit Breaker

File: `src/doc_extract/adapters/gemini_adapter.py` (update existing)

Add circuit breaker to the extraction method:

```python
"""Gemini LLM adapter using PydanticAI with circuit breaker."""
import os
from typing import Type
from pydantic import BaseModel
import time

from pydantic_ai import Agent, DocumentUrl
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from doc_extract.ports.llm import (
    LLMPort, ExtractionRequest, ExtractionResponse, LLMError
)
from doc_extract.core.logging import logger
from doc_extract.core.circuit_breaker import get_circuit_breaker


class GeminiAdapter(LLMPort):
    """Gemini API implementation with circuit breaker and resilience."""
    
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY required")
        
        self.provider = GoogleProvider(api_key=self.api_key)
        self.model = GoogleModel(model_name, provider=self.provider)
        
        # Initialize circuit breaker for Gemini
        self._circuit_breaker = get_circuit_breaker("gemini")
        
        logger.info(f"Initialized GeminiAdapter with model {model_name}")
    
    async def extract_structured(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data with circuit breaker protection."""
        start_time = time.time()
        
        try:
            # Execute with circuit breaker
            result = await self._circuit_breaker.call(
                self._do_extraction, request
            )
            return result
            
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit open for Gemini: {e}")
            raise LLMError(
                error_type="CIRCUIT_OPEN",
                message=f"Service temporarily unavailable: {e}",
                recoverable=True,
                retry_after=e.retry_after
            )
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            error_msg = str(e).lower()
            recoverable = any([
                "rate limit" in error_msg,
                "timeout" in error_msg,
                "503" in error_msg,
                "429" in error_msg
            ])
            
            raise LLMError(
                error_type="EXTRACTION_FAILED",
                message=str(e),
                recoverable=recoverable,
                retry_after_seconds=60 if recoverable else None
            )
    
    async def _do_extraction(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Actual extraction logic (called by circuit breaker)."""
        from doc_extract.core.circuit_breaker import CircuitBreakerOpen
        
        try:
            agent = Agent(
                model=self.model,
                system_prompt=request.system_prompt or self._default_system_prompt(),
                output_type=request.output_schema,
            )
            
            doc_url = DocumentUrl(url=request.document_url)
            
            result = await agent.run([
                f"Extract structured data from this {request.document_type} document.",
                doc_url
            ])
            
            processing_time = time.time()
            
            return ExtractionResponse(
                extracted_data=result.output,
                raw_output=result.output.model_dump_json() if hasattr(result.output, 'model_dump_json') else str(result.output),
                token_usage={
                    "input_tokens": getattr(result, 'input_tokens', 0),
                    "output_tokens": getattr(result, 'output_tokens', 0),
                },
                confidence_score=0.85,  # Default, could extract from result
                processing_time_seconds=processing_time,
                model_name=self.model_name
            )
            
        except Exception as e:
            # Re-raise for circuit breaker to handle
            raise
    
    # ... rest of existing methods
```

### 3. Add Health Endpoint for Circuit Breakers

File: `src/doc_extract/api/resilience_endpoints.py`

```python
"""Resilience and monitoring endpoints."""
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
    """Get health status of all circuit breakers.
    
    Returns the state of each circuit (closed, open, half_open)
    and statistics on calls, failures, and rejections.
    """
    import datetime
    
    return CircuitHealthResponse(
        circuits=circuit_breaker_manager.get_all_health(),
        timestamp=datetime.datetime.utcnow().isoformat()
    )


@router.post("/resilience/circuits/{circuit_name}/reset")
async def reset_circuit(circuit_name: str):
    """Manually reset a circuit breaker.
    
    Useful for testing or after maintenance.
    """
    cb = circuit_breaker_manager.get_or_create(circuit_name)
    await cb.reset()
    
    return {"message": f"Circuit '{circuit_name}' has been reset"}


@router.get("/resilience/status")
async def get_resilience_status():
    """Get overall system resilience status."""
    return {
        "circuit_breakers": len(circuit_breaker_manager._breakers),
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
```

### 4. Update API Main to Include Resilience Endpoints

File: `src/doc_extract/api/main.py`

```python
# Add imports
from doc_extract.api.resilience_endpoints import router as resilience_router

# Add to app (after other routers)
app.include_router(resilience_router)
```

## Deliverables

- [ ] src/doc_extract/core/circuit_breaker.py - Circuit breaker implementation
- [ ] src/doc_extract/adapters/gemini_adapter.py - Updated with circuit breaker
- [ ] src/doc_extract/api/resilience_endpoints.py - Health endpoints
- [ ] src/doc_extract/api/main.py - Include resilience router
- [ ] tests/test_circuit_breaker.py - Unit tests

## Success Criteria

1. Circuit opens after 5 consecutive failures
2. Requests are rejected when circuit is open
3. Circuit recovers after 30 seconds (half-open)
4. Recovery requires 3 successful calls
5. Health endpoint shows circuit status

## Testing

```bash
# Test circuit breaker
curl http://localhost:8000/api/v1/resilience/circuits

# Should show:
# {
#   "circuits": {
#     "gemini": {
#       "name": "gemini",
#       "state": "closed",
#       "failure_count": 0,
#       "stats": {...}
#     }
#   }
# }
```
