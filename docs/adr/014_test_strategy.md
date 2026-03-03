# ADR 014: Test Strategy with pytest

## Status
**Accepted** - 2026-03-02

## Context
We need a comprehensive testing strategy to ensure code quality and prevent regressions. The assignment encourages test coverage for critical paths.

## Purpose
This decision impacts:
- **Code Quality**: How we maintain reliability
- **Confidence**: How we trust our code
- **Regression Prevention**: How we catch bugs early
- **Documentation**: Tests as specification

## Alternatives Considered

| Alternative | Speed | DX | Best For |
|-------------|-------|-----|----------|
| **pytest (Chosen)** | Fast | Excellent | Python projects |
| unittest | Fast | Basic | Simple projects |
| Hypothesis | Medium | Good | Property-based testing |
| pytest-asyncio | Fast | Good | Async code |
| pytest-cov | Fast | Good | Coverage tracking |

## Detailed Pros and Cons

### pytest (Chosen)

**Pros:**
- **Simple syntax** - Easy to read and write
- **Great fixtures** - Clean setup/teardown
- **Rich ecosystem** - Many plugins
- **Async support** - pytest-asyncio works well
- **Great output** - Clear failure messages
- **Parameterization** - Test once, run many variations
- **Fixtures as dependencies** - Clean test design
- **Coverage** - pytest-cov integration

**Cons:**
- **Learning curve** - Fixtures, markers take time
- **Magic** - Some behavior is implicit
- **Async complexity** - Must configure properly

### unittest

**Pros:**
- **Standard library** - No dependencies
- **Familiar** - JUnit-style

**Cons:**
- **Verbose** - More boilerplate
- **Less features** - Missing pytest's conveniences

### Hypothesis

**Pros:**
- **Property-based** - Test many inputs
- **Finds edge cases** - Automated edge case discovery

**Cons:**
- **Complex** - Requires different thinking
- **Slow** - Can be slow to run

## Conclusion

We chose **pytest with pytest-asyncio and pytest-cov** because:

1. **Industry standard** - Most Python projects use pytest
2. **Async support** - Our code is async-native
3. **Coverage** - Assignment encourages test coverage
4. **Speed** - Fast test execution
5. **Clarity** - Readable test code

## Test Organization

```
tests/
├── __init__.py
├── test_domain.py       # Domain model tests
├── test_adapters.py     # Adapter tests
├── test_api.py          # API endpoint tests
├── test_services.py    # Service layer tests
├── test_ports.py       # Port interface tests
├── test_validation.py # Validation tests
├── test_edge_cases.py  # Edge case handling
├── test_sqlite_adapter.py # Database tests
├── test_minio_adapter.py # Storage tests
├── integration/
│   └── __init__.py
└── evaluation/
    ├── __init__.py
    ├── run_eval.py     # Evaluation script
    └── golden_set.json # Test data
```

## Test Types

### Unit Tests
- Domain model validation
- Adapter functionality
- Port interfaces
- Error handling

### Integration Tests
- API endpoints
- Database operations
- Storage operations

### Evaluation Tests
- Golden set extraction
- Accuracy metrics

## Running Tests

```bash
# Run all tests with coverage
just test

# Run specific test file
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ --cov=src/doc_extract --cov-report=term-missing
```

## Test Coverage Goals

| Component | Target | Status |
|-----------|--------|--------|
| Domain | 90%+ | ✅ |
| Adapters | 80%+ | ✅ |
| API | 85%+ | ✅ |
| Services | 80%+ | ✅ |
| Ports | 90%+ | ✅ |
| **Overall** | **80%+** | ✅ |

## Consequences

### Positive
- Fast test execution
- Clear failure messages
- Easy to add new tests
- Great for TDD
- CI integration

### Negative
- Fixture complexity
- Async test setup
- Coverage can be misleading

## Implementation

See:
- `tests/` - Test files
- `pyproject.toml` - pytest configuration
- `Justfile` - test command

## Review Schedule
Review quarterly to assess coverage and add new tests as needed.