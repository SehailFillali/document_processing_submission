# ADR 020: Multi-Critic Panel for Quality Assurance (Future)

## Status
**Partially Implemented** - 2026-03-02

## Context
Extraction accuracy is critical for financial documents. A single LLM extraction can hallucinate or misread values. The reference implementation uses a "Panel of Critics" — multiple LLM agents (2x Gemini + 1x Claude) that independently verify extractions with a "Unanimous Pass" consensus policy.

## Current Implementation
We implement a **single critic agent** with a self-correction loop (Prompt 22). This provides the core benefit (automated verification + retry) without the complexity of multi-model consensus.

## Future: Full Panel

| Approach | Accuracy | Cost | Latency | Complexity |
|----------|----------|------|---------|------------|
| No critic | Low | Low | Low | Low |
| **Single critic + retry (Current)** | Medium-High | Medium | Medium | Medium |
| Multi-critic panel | Very High | High | Medium (parallel) | High |

### Planned Panel Configuration
```python
CRITIC_PANEL_CONFIG = [
    {"name": "gemini_critic_1", "model": "gemini-2.5-pro", "temperature": 0.0},
    {"name": "gemini_critic_2", "model": "gemini-2.5-pro", "temperature": 0.4},
    {"name": "claude_critic", "model": "claude-opus-4-5", "temperature": 0.0},
]
```

### Why Multiple Models at Different Temperatures
- **Temperature 0.0**: Deterministic, consistent — catches obvious errors
- **Temperature 0.4**: Slightly creative — catches ambiguous interpretations
- **Different providers**: Model-level diversity reduces correlated errors (if Gemini systematically misreads a format, Claude may catch it)

### Consensus Policy: Unanimous Pass
A metric only passes if ALL critics confirm it as correct. This is strict by design:
- Any single dissent flags the metric for review
- Dissenting critics provide `correct_value` and `note` for feedback
- Synthesized feedback is passed back to the extraction agent on retry

### Blended QA Score
```
global_qa_score = (critic_score * 0.5) + (token_logprob_score * 0.5)
```

Where:
- `critic_score` = percentage of metrics unanimously confirmed correct
- `token_logprob_score` = average token-level confidence from LLM log probabilities

### Parallel Execution with Quorum
```python
results = await asyncio.gather(*critic_tasks, return_exceptions=True)
# Quorum: need at least 1 successful response
# Track non-responsive critics for observability
```

## Conclusion
The single-critic approach provides 80% of the value at 30% of the complexity. The full panel is a Phase 2 enhancement for production deployment where accuracy requirements justify the additional cost (~3x LLM calls per extraction).

## Consequences

### Positive (Current Single Critic)
- Catches most extraction errors
- Self-correction improves accuracy over iterations
- Feedback notes give the extraction agent specific guidance
- Graceful degradation if critic fails

### Positive (Future Multi-Critic)
- Cross-model validation eliminates correlated errors
- Temperature diversity catches ambiguous interpretations
- Parallel execution keeps latency manageable

### Negative (Future Multi-Critic)
- 3x cost per extraction for critic calls
- More complex error handling (partial panel failures)
- Need to maintain multiple provider adapters

## Implementation Timeline
Phase 2: After MVP submission. Requires multi-provider adapter support and configurable panel settings.
