# ADR 016: Circuit Breaker & Resilience Patterns

## Status
**Accepted** - 2026-03-02

## Context
We need production-grade resilience patterns to handle LLM failures gracefully and prevent cascade failures when external services are unavailable. This is a "Head of Engineering" level feature demonstrating operational excellence.

## Purpose
This decision impacts:
- **Reliability**: How we handle service failures
- **Availability**: Preventing total system outages
- **Recovery**: Fast recovery from failures
- **Observability**: Understanding failure patterns

## Alternatives Considered

| Alternative | Pros | Cons | Best For |
|-------------|------|------|----------|
| **stamina (Chosen)** | Built-in retry + circuit breaker | Newer library | Python apps |
| pybreaker | Mature circuit breaker | No retry built-in | Simple CB |
| Tenacity | Good retry logic | No circuit breaker | Retry-heavy |
| Manual implementation | Full control | Reinventing the wheel | Custom needs |
| No circuit breaker | Simple | Cascading failures | Non-critical |

## Detailed Pros and Cons

### stamina (Chosen)

**Pros:**
- **Combined patterns** - Retry + circuit breaker + backoff
- **Async native** - Built for async Python
- **Simple API** - Easy to configure
- **Configurable** - Many options for tuning
- **Pythonic** - Works well with modern Python

**Cons:**
- **Newer library** - Less community knowledge
- **Active development** - API may change

### pybreaker

**Pros:**
- **Mature** - Long history
- **Simple** - Easy to understand

**Cons:**
- **No retry** - Need separate library
- **Sync-focused** - Async requires wrapper

### Tenacity

**Pros:**
- **Feature-rich** - Many retry options
- **Well-documented** - Good docs

**Cons:**
- **No circuit breaker** - Only retry
- **Complex** - Many options to learn

## Conclusion

We chose **stamina** because:

1. **Combines retry + circuit breaker** - Single library for both
2. **Async native** - Built for async/await
3. **Simple configuration** - Easy to get started
4. **Industry best practice** - Resilience patterns expected at scale
5. **Head of Engineering** - Demonstrates operational thinking

## Implementation

### Circuit Breaker States

```
Closed → Open → Half-Open
  │        │         │
  │        │         ↓
  │        │      Testing
  │        │         │
  │        └─────────┘
  ↓
Normal Operation
```

### Configuration

```python
from stamina import retry

@retry(
    attempts=3,
    wait_initial=1.0,
    wait_max=30.0,
    wait_jitter=2.0,
)
async def call_llm():
    # Protected call
```

### Usage in LLM Adapter

```python
from stamina import retry

class OpenAIAdapter:
    @retry(
        attempts=3,
        wait_initial=1.0,
        wait_max=30.0,
        on_retry=lambda ctx: logger.warning(f"Retry {ctx.attempt}")
    )
    async def extract_structured(self, request):
        # LLM call with automatic retry + circuit breaker
```

## Consequences

### Positive
- Prevents cascade failures
- Automatic recovery from transient errors
- Configurable retry behavior
- Built-in backoff
- Logging of retry attempts

### Negative
- Additional complexity
- Requires tuning for each service
- May mask underlying issues if not monitored

## Implementation

See:
- `src/doc_extract/core/circuit_breaker.py` - Circuit breaker (planned)
- Uses stamina library already in pyproject.toml

## Review Schedule
Review after 3 months to assess if resilience patterns are working as expected.