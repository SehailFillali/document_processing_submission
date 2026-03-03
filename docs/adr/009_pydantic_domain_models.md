# ADR 009: Domain Model Design with Pydantic v2

## Status
**Accepted** - 2026-03-02

## Context
We need to define the core data structures for document extraction. The loan documents use case requires extracting borrower PII, income history, and account information with full provenance tracking. We chose Pydantic v2 for validation, but we need to decide on the modeling approach.

## Purpose
This decision impacts:
- **Data Quality**: How strictly we validate extracted data
- **Extensibility**: How easily we can add new document types
- **Interoperability**: How well we integrate with downstream systems
- **Developer Experience**: How intuitive the models are to work with

## Alternatives Considered

| Alternative | Description | Type Safety | Flexibility | Complexity |
|-------------|-------------|-------------|-------------|------------|
| **Pydantic v2 Strict (Chosen)** | Native Pydantic with strict mode | Very High | Medium | Low |
| Pydantic v1 | Legacy Pydantic | High | Medium | Low |
| attrs + cattrs | Alternative to Pydantic | Medium | High | Medium |
| dataclasses + manual | Pure stdlib approach | Low | Low | Low |
| msgspec | Rust-based, fastest | Very High | Low | Medium |
| SQLAlchemy models | ORM-based | Medium | Medium | High |

## Detailed Pros and Cons

### Pydantic v2 Strict Mode (Chosen)

**Pros:**
- **Built-in JSON schema generation** - Automatic OpenAPI support
- **Strict validation** - Fail on extra fields, enforces types
- **Computed fields** - Easy confidence score calculations
- **Field validators** - Custom validation with @field_validator
- **Model validation** - Cross-field validation with @model_validator
- **Provenance support** - Native support for tracking extraction sources
- **Type coercion** - Automatic type conversion (e.g., string to date)
- **Mypy plugin** - Deep integration with type checkers
- **Active development** - Pydantic team is very active
- **PydanticAI integration** - Native integration for LLM output validation

**Cons:**
- **Learning curve** - Many features to learn
- **Strict mode overhead** - Initial development slightly slower
- **Performance** - Slightly slower than msgspec (negligible for most use cases)
- **Lock-in** - Tight coupling to Pydantic ecosystem

### attrs + cattrs

**Pros:**
- **Mature** - Longer history than Pydantic
- **Flexible** - More customization options
- **Similar to Pydantic** - Easy to migrate

**Cons:**
- **Additional dependency** - Two libraries needed
- **Less adoption** - Smaller ecosystem
- **JSON schema** - Not as good as Pydantic

### msgspec

**Pros:**
- **Fastest** - 10x faster than Pydantic for some operations
- **Minimal dependencies** - No Python runtime deps

**Cons:**
- **Less flexible** - Less customization
- **Smaller community** - Fewer resources
- **Newer** - Less battle-tested

### Pure dataclasses

**Pros:**
- **No dependencies** - Standard library only
- **Simple** - Easy to understand

**Cons:**
- **Manual validation** - Must write all validators
- **No schema generation** - Must build manually
- **No type coercion** - Must handle yourself
- **Error messages** - Not as helpful

## Conclusion

We chose **Pydantic v2 Strict Mode** because:

1. **PydanticAI integration** - The extraction agent works natively with Pydantic schemas
2. **Schema auto-generation** - Automatic OpenAPI docs and JSON schemas
3. **Provenance tracking** - Natural fit for tracking extraction sources
4. **Industry standard** - Most Python devs know Pydantic
5. **Validation UX** - Clear error messages accelerate development
6. **Future-proof** - v3 is in development with even better performance

The "strict" mode ensures data quality at the cost of minor development overhead - acceptable for an MVP where correctness matters.

## Consequences

### Positive
- Automatic API documentation via OpenAPI
- Type-safe extraction with PydanticAI
- Clear validation errors for developers
- Confidence score computation is trivial
- Easy JSON serialization/deserialization
- Source tracking via Provenance model

### Negative
- Must be explicit about all fields
- Some overhead defining validators
- Need to understand strict vs non-strict modes
- Potential performance hit on very high-volume use

## Implementation

See:
- `src/doc_extract/domain/base.py` - DomainModel, Provenance, MissingField
- `src/doc_extract/domain/borrower.py` - BorrowerProfile, Address, IncomeEntry
- `src/doc_extract/domain/submission.py` - DocumentSubmission, SubmissionStatus
- `src/doc_extract/domain/validation.py` - ValidationResult, ValidationReport

### Key Design Patterns

1. **Strict Mode**: All models use `strict=True` to prevent silent type coercion bugs
2. **Provenance**: Every extracted field tracks source document, page, and confidence
3. **MissingField**: Explicit type for missing data (not None) to distinguish "didn't extract" from "not present"
4. **Optional Fields**: Most borrower fields are Optional to support partial extraction
5. **Validation**: Custom validators for dates, amounts, and field consistency

## Review Schedule
Review in 6 months to assess if strict validation approach is working or if too many false positives occur.
