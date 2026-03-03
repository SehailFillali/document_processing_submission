# Prompt 21: Achieve 80%+ Test Coverage with Smart Tests

## Status
[COMPLETED]

## Context

Current test coverage is **54%** (731 of 1586 statements missed). We need to exceed 80% with tests that protect against real bugs and edge cases, not just line-counting exercises.

## Current Coverage Gaps (by priority)

### Critical: 0% Coverage (must test with mocks)
| Module | Stmts | Miss | Why Untested |
|--------|-------|------|-------------|
| `services/graph.py` | 138 | 138 | Pydantic Graph nodes - needs mock LLM |
| `adapters/gcs_storage.py` | 83 | 83 | GCP dependency - needs mock |
| `adapters/pubsub_adapter.py` | 72 | 72 | GCP dependency - needs mock |
| `adapters/gemini_adapter.py` | 60 | 60 | API key required - needs mock |

### High: Under 50% Coverage
| Module | Stmts | Miss | Cover | Key Missing Lines |
|--------|-------|------|-------|------------------|
| `adapters/minio_adapter.py` | 113 | 90 | 20% | All async methods (upload/download/delete/exists) |
| `adapters/openai_adapter.py` | 37 | 22 | 41% | extract_structured, validate_connection |
| `core/circuit_breaker.py` | 107 | 66 | 38% | call(), state transitions, stats |
| `core/observability.py` | 54 | 32 | 41% | calculate_cost, check_budget, logfire init |
| `adapters/storage_factory.py` | 17 | 9 | 47% | minio and s3 branches |
| `api/blob_endpoints.py` | 73 | 38 | 48% | process_from_blob happy path |
| `api/observability_endpoints.py` | 45 | 23 | 49% | cost and metrics endpoints |

### Medium: Under 80% Coverage  
| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `core/exceptions.py` | 25 | 11 | 56% |
| `api/resilience_endpoints.py` | 19 | 5 | 74% |
| `api/main.py` | 100 | 23 | 77% |
| `ports/llm.py` | 37 | 8 | 78% |

## Strategy

### 1. Mock External Services
- Mock `pydantic_ai.Agent` for Gemini/OpenAI adapters
- Mock `google.cloud.storage` for GCS adapter
- Mock `google.cloud.pubsub_v1` for Pub/Sub adapter
- Mock `minio.Minio` for MinIO adapter
- Use `unittest.mock.AsyncMock` for async methods

### 2. Test Circuit Breaker State Machine
- Test CLOSED -> OPEN transition after N failures
- Test OPEN -> HALF_OPEN after timeout
- Test HALF_OPEN -> CLOSED after M successes
- Test rejected calls when OPEN
- Test stats tracking

### 3. Test Graph Nodes Independently
- PreprocessNode: file exists/missing, size limits
- ValidateNode: valid profile, missing fields, low confidence
- ExtractNode: mock LLM response

### 4. Test Observability Without Logfire
- Cost calculation with known token counts
- Budget checking at various thresholds
- Endpoints returning correct data

### 5. Test Error Handling Paths
- Structured error responses (DocExtractError.to_dict())
- Rate limiter blocking and headers
- Exception handler middleware

## Requirements

### File: `tests/test_circuit_breaker.py`

Test the circuit breaker state machine:
- `test_closed_allows_calls` - Normal operation
- `test_opens_after_failure_threshold` - 5 failures opens circuit
- `test_rejects_when_open` - CircuitBreakerOpen raised
- `test_half_open_after_timeout` - State transitions after timeout
- `test_closes_after_success_threshold` - 3 successes close circuit
- `test_stats_tracking` - Counters are accurate
- `test_manager_get_or_create` - Manager creates/reuses breakers
- `test_manager_get_all_health` - Health report
- `test_reset` - Manual reset works

### File: `tests/test_observability.py`

Test observability and cost tracking:
- `test_calculate_cost` - Known token counts produce correct cost
- `test_check_budget_ok` - Under budget
- `test_check_budget_warning` - Over warning threshold
- `test_check_budget_exceeded` - Over budget
- `test_obs_context_disabled` - No-op when disabled
- `test_cost_endpoints` - API returns cost data
- `test_metrics_endpoint` - API returns metrics

### File: `tests/test_error_handling.py`

Test error codes, exceptions, and rate limiting:
- `test_error_code_to_status_mapping` - All codes map to HTTP status
- `test_doc_extract_error_to_dict` - Serialization
- `test_rate_limiter_allows_under_limit` - Normal requests pass
- `test_rate_limiter_blocks_over_limit` - Excess requests blocked
- `test_rate_limit_headers` - X-RateLimit-* headers present
- `test_error_codes_endpoint` - /api/v1/errors/codes returns all codes
- `test_exception_handler` - DocExtractError returns structured JSON

### File: `tests/test_graph_nodes.py`

Test processing graph nodes with mocks:
- `test_preprocess_file_exists` - Happy path
- `test_preprocess_file_missing` - Returns End with error
- `test_preprocess_file_too_large` - Size limit enforcement
- `test_validate_valid_profile` - Complete valid profile
- `test_validate_missing_name` - Manual review triggered
- `test_validate_low_confidence` - Warning generated
- `test_validate_empty_extraction` - Error handling

### File: `tests/test_adapters_mock.py`

Test cloud adapters with mocked dependencies:
- `test_gcs_upload` - Mock google.cloud.storage
- `test_gcs_download` - Mock blob.download_as_bytes
- `test_gcs_exists` - Mock blob.exists
- `test_pubsub_publish` - Mock publisher
- `test_pubsub_acknowledge` - Returns True
- `test_openai_extract` - Mock AsyncOpenAI
- `test_storage_factory_local` - Returns LocalFileSystemAdapter
- `test_storage_factory_minio` - Returns MinIOAdapter
- `test_gemini_extract` - Mock pydantic_ai Agent

## Coverage Target

| Category | Current | Target |
|----------|---------|--------|
| Overall | 54% | 80%+ |
| Core modules | ~60% | 90%+ |
| Adapters | ~30% | 75%+ |
| API endpoints | ~60% | 85%+ |
| Services | ~40% | 80%+ |

## Success Criteria

1. `pytest --cov=doc_extract` shows **80%+ overall coverage**
2. No module below 60% coverage
3. All tests pass
4. Tests catch real bugs (not just line coverage)
5. Mocks are realistic (match actual API signatures)

## Testing Command

```bash
.venv/bin/python -m pytest tests/ --cov=doc_extract --cov-report=term-missing -q
```
