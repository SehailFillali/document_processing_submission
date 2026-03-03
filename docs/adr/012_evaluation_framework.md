# ADR 012: Evaluation Framework with Golden Set

## Status
**Accepted** - 2026-03-02

## Context
We need to validate that the document extraction system produces accurate results. The assignment requires test coverage, and we need a systematic way to measure extraction quality.

## Purpose
This decision impacts:
- **Quality Assurance**: How we verify extraction accuracy
- **Confidence**: How we trust extracted data
- **Regression Prevention**: How we catch breaking changes
- **Iteration**: How we measure improvements
- **Stakeholder Trust**: How we demonstrate system reliability

## Alternatives Considered

| Alternative | Setup Effort | Accuracy | Automation | Best For |
|-------------|--------------|----------|------------|----------|
| **Golden Set (Chosen)** | Medium | High | Yes | Structured extraction |
| Manual Review | Low | High | No | Small scale |
| Synthetic Data | Low | Low | Yes | Rapid prototyping |
| LLM-as-Judge | Medium | Medium | Yes | Complex extractions |
| A/B Testing | High | Medium | Yes | Production monitoring |

## Detailed Pros and Cons

### Golden Set (Chosen)

**Pros:**
- **Ground truth** - Known correct outputs for comparison
- **Reproducible** - Same test data every run
- **Automated** - CI/CD integration
- **Metrics** - Precision, recall, F1 scores
- **Regression detection** - Catches quality degradation

**Cons:**
- **Setup effort** - Need to manually create golden examples
- **Maintenance** - Must update as schemas evolve
- **Coverage** - Limited to known document types
- **Curation** - Need expert knowledge to create accurate golden data

### Manual Review

**Pros:**
- **Accurate** - Human judgment
- **Simple** - No infrastructure needed

**Cons:**
- **Slow** - Can't scale
- **Inconsistent** - Different reviewers, different results
- **Expensive** - Human time costs money

### Synthetic Data

**Pros:**
- **Easy to generate** - No manual effort
- **Unlimited** - Can create any quantity

**Cons:**
- **Unrealistic** - Doesn't match real documents
- **Noisy** - May miss edge cases
- **Not validated** - Quality unknown

### LLM-as-Judge

**Pros:**
- **Scalable** - Can evaluate many samples
- **Contextual** - Understands extraction goals
- **Automated** - No manual review needed

**Cons:**
- **Expensive** - Costs for LLM calls
- **Inconsistent** - May have different standards
- **Hallucination** - May approve bad extractions

## Conclusion

We chose **Golden Set with Automated Metrics** because:

1. **Assignment requirement** - Test coverage encouraged
2. **Accuracy** - We need to verify extraction quality
3. **Reproducibility** - Same tests every time
4. **CI/CD** - Can run in automated pipelines
5. **Gradual improvement** - Add more golden examples over time

## Implementation

### Golden Set Format
```json
{
  "document_id": "loan_001",
  "document_path": "tests/evaluation/data/loan_001.pdf",
  "expected_output": {
    "name": "John Doe",
    "address": {
      "street": "123 Main St",
      "city": "Springfield",
      "state": "IL",
      "zip_code": "62701"
    },
    "income_history": [
      {
        "amount": 75000,
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "source": "Employer Inc"
      }
    ]
  }
}
```

### Evaluation Metrics
- **Field-level accuracy**: Each extracted field matches golden
- **Missing field rate**: Percentage of required fields not extracted
- **Confidence correlation**: LLM confidence vs actual accuracy
- **Processing time**: Performance regression detection

## Evaluation Script

See:
- `tests/evaluation/run_eval.py` - Main evaluation script
- `tests/evaluation/golden_set.json` - Test data

### Running Evaluation

```bash
just evaluate
```

This will:
1. Load golden set documents
2. Run extraction pipeline
3. Compare outputs to expected
4. Report accuracy metrics

## Consequences

### Positive
- Automated quality measurement
- Catches regressions before deployment
- Objective metrics for extraction quality
- Easy to add more test cases

### Negative
- Initial setup requires manual curation
- Must maintain golden set as schemas evolve
- Limited to curated document types

## Review Schedule
Review quarterly to assess golden set coverage and add new test cases.