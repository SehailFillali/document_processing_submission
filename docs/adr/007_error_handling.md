# ADR 007: Error Handling and Data Quality Strategy

## Status
**Accepted** - 2026-03-02

## Context
LLM extraction can fail partially or completely. We need a strategy to:
- Handle errors gracefully
- Provide partial results when possible
- Track data quality with confidence scores
- Route failures to manual review

## Decision
Multi-layered error handling with:
1. **Fail-fast**: Validation at API entry
2. **Retry with backoff**: Transient LLM failures
3. **Partial success**: Return valid fields + error list
4. **Dead Letter Queue**: Complete failures for investigation

## Error Categories

| Category | Handling | User Impact |
|----------|----------|-------------|
| Validation (400) | Fail fast, reject | Immediate feedback |
| LLM Timeout (502) | Retry 3x, then queue | Delayed response |
| Partial Extract | Return valid + errors | Partial data + review |
| Complete Failure (500) | DLQ + notification | Manual review |

## Confidence Scoring

```python
@dataclass
class Provenance:
    source_document: str
    source_page: int | None
    verbatim_text: str | None
    confidence_score: float = Field(ge=0.0, le=1.0)

# Thresholds
HIGH_CONFIDENCE = 0.9
MEDIUM_CONFIDENCE = 0.7
LOW_CONFIDENCE = 0.5

if profile.extraction_confidence >= HIGH_CONFIDENCE:
    status = "completed"
elif profile.extraction_confidence >= MEDIUM_CONFIDENCE:
    status = "partial"  # Review recommended
else:
    status = "manual_review"  # Required
```

## Validation Rules

1. **Required fields**: name, address must be present
2. **Income positive**: All amounts > 0
3. **Date validity**: period_end > period_start
4. **Confidence threshold**: >= 0.8 for auto-complete

## Consequences

- **Positive**: Robust error handling, data quality tracking
- **Negative**: Complexity in error routing

## Review Schedule
Review after 1 month of production to assess error rates.
