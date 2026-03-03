# ADR 021: Token Log-Probability Confidence Scoring (Future)

## Status
**Proposed** - 2026-03-02 (Not yet implemented)

## Context
The reference implementation calculates per-metric confidence scores by analyzing token-level log probabilities from the LLM response. This provides a model-native measure of certainty for each extracted value, independent of the critic agent's assessment.

## Purpose
Provide a second, orthogonal quality signal that doesn't depend on another LLM call. Token logprobs measure how "sure" the model was when generating each value.

## How It Works

1. **Request logprobs** from the LLM alongside the extraction response
2. **Reconstruct token stream**: Build a character-to-token index mapping
3. **Align tokens to metric values** using regex pattern matching against the raw output text
4. **Calculate per-metric confidence**: Average the log probabilities of tokens that correspond to each metric's value
5. **Convert to score**: `confidence = exp(avg_logprob) * 100`

### Example

For a metric `total_revenue = 1250000.0`:
- Find tokens: `["125", "000", "0", ".0"]`
- Log probs: `[-0.01, -0.02, -0.05, -0.01]`
- Average logprob: `-0.0225`
- Confidence: `exp(-0.0225) * 100 = 97.8%`

A low-confidence extraction (model was uncertain):
- Metric `accounts_receivable = 45000.0`
- Log probs: `[-0.8, -1.2, -0.5]`
- Average logprob: `-0.833`
- Confidence: `exp(-0.833) * 100 = 43.5%`

## Alternatives Considered

| Approach | Cost | Independence | Granularity |
|----------|------|-------------|-------------|
| **Token logprobs (Planned)** | Free (part of response) | High | Per-field |
| Critic agent score | Extra LLM call | Medium | Per-field |
| Self-reported confidence | Free | Low (model bias) | Per-field |
| Embedding similarity | Moderate | High | Per-document |
| Repeated extraction variance | High (multiple calls) | High | Per-field |

## Integration with QA Score

The token logprob score is blended with the critic score:

```python
def calculate_global_qa_score(
    critic_score: float | None,
    token_score: float | None,
    critic_weight: float = 0.5,
) -> float:
    if critic_score is None and token_score is None:
        return 0.0
    if critic_score is None:
        return token_score
    if token_score is None:
        return critic_score
    return (critic_score * critic_weight) + (token_score * (1 - critic_weight))
```

## Provider Support

| Provider | Logprob Support | Notes |
|----------|----------------|-------|
| Google Gemini (VertexAI) | Yes | Via `google_include_log_probs=True` |
| OpenAI | Yes | Via `logprobs=True` parameter |
| Anthropic (Claude) | No | Not currently supported |

## Conclusion
Token logprobs are the only approach that is both free and independent of another LLM call. Combined with the critic score in a blended formula, they provide robust, multi-signal quality measurement. The per-field granularity enables targeted flagging of uncertain extractions for manual review.

## Consequences

### Positive
- No additional cost (logprobs are part of the response)
- Independent from critic agent (orthogonal signal)
- Per-field granularity
- Enables automatic flagging of uncertain fields

### Negative
- Provider-specific implementation (different logprob formats)
- Regex-based token alignment can be fragile
- Not available for all providers (Anthropic)
- Requires careful handling of multi-token values

## Implementation Timeline
Phase 2: Requires provider-specific logprob support. Start with OpenAI (simpler API), then add Gemini VertexAI.
