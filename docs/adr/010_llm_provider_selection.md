# ADR 010: LLM Provider Selection and PydanticAI Strategy

## Status
**Accepted** - 2026-03-02

## Context
We need to select an LLM provider for document extraction. The assignment requires extracting structured data from loan documents. We initially planned to use Gemini, but the implementation uses OpenAI. This ADR documents the final decision.

## Purpose
This decision impacts:
- **Extraction Quality**: How accurately the LLM extracts data
- **Cost**: API pricing for document processing
- **Latency**: Response time for extraction
- **Setup Complexity**: How easy it is for reviewers to run
- **Vendor Lock-in**: How dependent we are on one provider

## Alternatives Considered

| Alternative | Cost (1K docs) | Setup Complexity | Quality | Speed |
|-------------|----------------|-------------------|---------|-------|
| **OpenAI gpt-4o-mini (Chosen)** | ~$0.15 | Easy | High | Fast |
| Gemini 1.5 Flash | ~$0.075 | Easy | High | Fast |
| Claude 3 Haiku | ~$0.25 | Medium | High | Fast |
| GPT-4 Turbo | ~$3.00 | Easy | Very High | Medium |
| Azure OpenAI | ~$0.15 | Complex | High | Fast |
| VertexAI (Gemini) | ~$0.075 | Complex | High | Fast |
| Local (Llama 3) | $0.00 | Very Complex | Medium | Slow |

## Detailed Analysis

### OpenAI gpt-4o-mini (Chosen)

**Pros:**
- **PydanticAI native support** - Easy integration with pydantic-ai library
- **Structured output** - Native JSON schema enforcement
- **Fast** - Optimized for speed
- **Reliable** - Very stable API
- **Well-documented** - Extensive examples
- **Token counting** - Built-in usage tracking

**Cons:**
- **Cost** - Not the cheapest (but cheap enough for MVP)
- **Data privacy** - Data leaves our infrastructure
- **Rate limits** - Can be restrictive at scale
- **API dependency** - Need internet access

### Gemini 1.5 Flash

**Pros:**
- **Cheapest** - Very competitive pricing
- **Large context** - 1M token context window
- **Native document support** - Can read PDFs directly
- **Google ecosystem** - Integrates with GCP

**Cons:**
- **PydanticAI integration** - Less mature than OpenAI
- **Schema enforcement** - Not as strict as OpenAI
- **Less predictable** - Output format varies more
- **Setup** - Requires API key from Google AI Studio

### Claude 3 Haiku (Anthropic)

**Pros:**
- **Excellent reasoning** - Strong for complex extraction
- **Good JSON output** - Reliable structured output

**Cons:**
- **Higher cost** - More expensive than alternatives
- **Different API style** - Not using standard OpenAI API
- **Less documentation** - Fewer PydanticAI examples

### VertexAI (Enterprise)

**Pros:**
- **Data privacy** - Data stays in GCP
- **Enterprise features** - Compliance, security
- **SLA guarantees** - Reliability guarantees

**Cons:**
- **Complex setup** - Requires GCP project, service account
- **Not suitable for assignment** - Reviewer can't easily run
- **Infrastructure needed** - Not a quick setup

## Decision: Dual Provider with OpenAI as Default

We implement **both** OpenAI and Gemini adapters, with OpenAI as the default because:

1. **PydanticAI native** - Best integration with our extraction pipeline
2. **Reviewer-friendly** - Easy to get OpenAI API key from platform
3. **Reliability** - OpenAI API is extremely stable
4. **Quality** - gpt-4o-mini is excellent for extraction
5. **Flexibility** - Can switch to Gemini for cost savings later

The architecture allows swapping via configuration:

```python
# OpenAI for production (default)
from doc_extract.adapters.openai_adapter import OpenAIAdapter

# Gemini available when needed
from doc_extract.adapters.gemini_adapter import GeminiAdapter
```

## Conclusion

We chose **OpenAI gpt-4o-mini as default** because:

1. **PydanticAI works best** - Native integration with pydantic-ai
2. **Reviewer setup** - Easier for assignment reviewer to get API key
3. **Quality sufficient** - gpt-4o-mini handles extraction well
4. **Cost acceptable** - $0.15/1000 docs is fine for MVP
5. **Flexibility** - Gemini adapter available for cost optimization later

This is a pragmatic choice balancing quality, ease of use, and architecture flexibility.

## Consequences

### Positive
- Easy to swap providers via configuration
- Both OpenAI and Gemini available
- Clear port/adapter pattern (see ADR 003, 004)
- Token usage tracking built-in
- Structured output guaranteed

### Negative
- Two adapters to maintain
- Need to test both for parity
- Configuration complexity
- Need to document which to use when

## Implementation

See:
- `src/doc_extract/ports/llm.py` - LLM port interface
- `src/doc_extract/adapters/openai_adapter.py` - OpenAI implementation
- `src/doc_extract/adapters/gemini_adapter.py` - Gemini implementation
- `src/doc_extract/services/processing.py` - Uses OpenAIAdapter by default

## Review Schedule
Review in 3 months to assess if extraction quality meets requirements. Consider switching to Gemini if:
- OpenAI costs become prohibitive
- Gemini's PydanticAI integration improves
- Need larger context window for complex documents
