# ADR 004: Use Pydantic Graph for Processing State Machine

## Status
**Accepted** - 2026-03-02

## Context
Document processing has multiple stages that need state tracking:
1. Preprocess: Validate file, check format
2. Extract: Call LLM, get structured data
3. Validate: Check data quality, confidence

We need type-safe state transitions with proper error handling.

## Decision
We will use **Pydantic Graph** for state machine orchestration with:
- Type-safe state transitions
- Automatic error routing to End states
- Clear node separation
- Observable execution flow

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Pydantic Graph (Chosen)** | Type-safe, native Pydantic | Newer library | N/A |
| Airflow | Mature, powerful | Heavy, complex | Overkill for sync pipeline |
| Temporal | Durable, reliable | Complex setup | Enterprise only |
| Simple Functions | No overhead | No state tracking | Can't track progress |

## Graph Structure

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Preprocess │ ──▶ │   Extract   │ ──▶ │  Validate   │
│    Node     │     │    Node     │     │    Node     │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
   End (error)         End (error)         End (result)
```

## Implementation

```python
from pydantic_graph import Graph, BaseNode, End

class PreprocessNode(BaseNode[PreprocessState]):
    async def run(self, state) -> ExtractNode | End[ErrorResult]:
        # Validate file, check size
        if errors:
            return End(ErrorResult(...))
        return ExtractNode(state=next_state)

class ExtractNode(BaseNode[ExtractState]):
    async def run(self, state) -> ValidateNode | End[ErrorResult]:
        # Call LLM
        return ValidateNode(state=extraction_result)

graph = Graph(nodes=[PreprocessNode, ExtractNode, ValidateNode])
```

## Consequences

- **Positive**: Type-safe, observable, easy to add human-in-loop
- **Negative**: Learning curve, additional dependency

## Review Schedule
Review after 3 months of production use.
