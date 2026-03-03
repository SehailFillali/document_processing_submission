# ADR 017: Logfire Observability & Cost Tracking

## Status
**Accepted** - 2026-03-02

## Context
We need production-grade observability with OpenTelemetry/Logfire integration to track costs, performance, and help debug issues. This is a "Head of Engineering" level feature demonstrating operational excellence.

## Purpose
This decision impacts:
- **Cost Control**: Tracking LLM token usage and costs
- **Performance**: Understanding latency bottlenecks
- **Debugging**: Tracing requests through the system
- **Monitoring**: Alerting on anomalies

## Alternatives Considered

| Alternative | Cost | Features | Best For |
|-------------|------|----------|----------|
| **Logfire (Chosen)** | Free tier | Full-stack | Python apps |
| OpenTelemetry | Free | Vendor-neutral | Enterprise |
| DataDog | $$$ | Full platform | Large teams |
| Prometheus + Grafana | Free | Metrics only | Self-hosted |
| Loguru + JSON | Free | Basic logging | Simple needs |

## Detailed Pros and Cons

### Logfire (Chosen)

**Pros:**
- **Pydantic integration** - Native support
- **Free tier** - Generous for development
- **Easy setup** - Few lines of code
- **Python-first** - Built for Python
- **Token tracking** - Built-in LLM cost tracking
- **Performance** - Low overhead

**Cons:**
- **Newer** - Less community knowledge
- **Vendor lock-in** - Pydantic Team's product
- **Limited to Python** - Not multi-language

### OpenTelemetry

**Pros:**
- **Vendor-neutral** - Export anywhere
- **Industry standard** - Widely adopted
- **Multi-language** - Works with any language

**Cons:**
- **Complex** - Steep learning curve
- **DIY** - Need to configure exporters
- **No built-in UI** - Need separate backend

### DataDog

**Pros:**
- **Full platform** - Everything included
- **Great UI** - Easy to use
- **Enterprise features** - Compliance, security

**Cons:**
- **Expensive** - Can cost thousands/month
- **Overkill** - Too much for MVP

### Prometheus + Grafana

**Pros:**
- **Free** - Open source
- **Industry standard** - Widely used
- **Flexible** - Custom metrics

**Cons:**
- **Self-hosted** - Need infrastructure
- **Metrics only** - No tracing/logging
- **Complex** - Multiple components

## Conclusion

We chose **Logfire** because:

1. **Pydantic ecosystem** - Native integration
2. **Free tier** - Sufficient for MVP
3. **Easy setup** - Quick to implement
4. **LLM cost tracking** - Built-in for our use case
5. **Head of Engineering** - Demonstrates operational thinking
6. **Low overhead** - Doesn't impact performance

## Implementation

### Basic Setup

```python
import logfire

logfire.configure()
logfire.info("Application started")
```

### Tracing

```python
with logfire.span("extract_document"):
    # Document extraction logic
    result = await llm.extract(...)
```

### Cost Tracking

```python
@logfire.inject_labels("cost")
async def extract_with_cost_tracking(request):
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[...]
    )
    
    # Automatic token tracking
    tokens = response.usage
    cost = calculate_cost(tokens)
    logfire.info(f"LLM call cost: ${cost:.4f}")
```

### Cost Dashboard Endpoint

```python
@app.get("/api/v1/costs")
async def get_costs():
    """Get cost summary for the period."""
    return {
        "total_cost": get_total_cost(),
        "by_model": get_cost_by_model(),
        "by_day": get_cost_by_day(),
    }
```

## Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| LLM Cost/Day | Total LLM spend | > $100/day |
| Request Latency | P95 response time | > 30s |
| Error Rate | Failed requests | > 5% |
| Queue Depth | Pending submissions | > 100 |

## Consequences

### Positive
- Automatic request tracing
- LLM cost tracking
- Performance monitoring
- Easy debugging with trace context
- Low overhead

### Negative
- External dependency (Logfire)
- Potential data privacy concerns
- Need to configure sampling for high volume

## Implementation

See:
- `src/doc_extract/core/observability.py` - Observability config (planned)
- Uses logfire library in pyproject.toml

## Review Schedule
Review after 1 month to assess if observability is providing value.