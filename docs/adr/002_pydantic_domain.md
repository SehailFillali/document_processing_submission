# ADR 002: Use Pydantic for Domain Modeling

## Status
**Accepted** - 2026-03-02

## Context
We need to model complex domain entities (BorrowerProfile, DocumentSubmission, etc.) with validation, serialization, and type safety. The system must handle nested structures, dates, and custom validation logic.

## Decision
We will use **Pydantic v2** for all domain modeling due to its:
- Native support for data validation
- JSON serialization/deserialization
- Type coercion and strict mode
- Integration with FastAPI

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Pydantic (Chosen)** | FastAPI native, validation, serialization | Runtime overhead | N/A |
| Dataclasses | Standard library, fast | Limited validation | Too basic |
| attrs | Mature, feature-rich | Less Pythonic | Extra dependency |
| Manual Classes | Full control | Reinventing wheel | Time sink |

## Implementation

```python
from pydantic import BaseModel, Field, field_validator
from datetime import date

class Address(BaseModel):
    street: str = Field(..., min_length=1)
    city: str
    state: str = Field(..., pattern=r"^[A-Z]{2}$")
    zip_code: str = Field(..., pattern=r"^\d{5}(-\d{4})?$")
    
    @field_validator("state")
    @classmethod
    def uppercase_state(cls, v: str) -> str:
        return v.upper()
```

## Consequences

- **Positive**: FastAPI auto-docs, validation, serialization built-in
- **Negative**: Runtime overhead for validation (minimal with v2)

## Review Schedule
Annual review for Pydantic v3 migration path.
