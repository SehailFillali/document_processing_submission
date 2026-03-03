# Prompt 24: Fix datetime.utcnow() Deprecation Warnings

## Status
[COMPLETED]

## Context

Python 3.12+ deprecates `datetime.datetime.utcnow()` (scheduled for removal in a future version). The correct replacement is `datetime.datetime.now(datetime.UTC)` which returns a timezone-aware UTC datetime. Our test suite currently produces **154 deprecation warnings** from 25 occurrences across 13 files. Cleaning these up signals attention to code quality and forward-compatibility.

## Objective

Replace every `datetime.utcnow()` call with the timezone-aware equivalent `datetime.now(datetime.UTC)`, ensuring all 236 tests continue to pass with zero deprecation warnings from our code.

## Requirements

### Migration Pattern

Every occurrence follows the same mechanical transformation:

```python
# BEFORE (deprecated)
datetime.utcnow()
datetime.datetime.utcnow()

# AFTER (correct)
datetime.now(datetime.UTC)
datetime.datetime.now(datetime.UTC)
```

**Import requirement:** Ensure `datetime.UTC` is accessible. In files that use `from datetime import datetime`, the `UTC` constant must also be imported:

```python
# If file uses: from datetime import datetime
from datetime import datetime, UTC
# Then use: datetime.now(UTC)

# If file uses: import datetime
# Then use: datetime.datetime.now(datetime.UTC)
```

### Files to Modify (25 occurrences, 13 files)

#### Source Code (14 occurrences, 8 files)

1. **`src/doc_extract/api/main.py`** (1 occurrence)
   - Line 90: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`

2. **`src/doc_extract/api/resilience_endpoints.py`** (2 occurrences)
   - Line 25: `datetime.datetime.utcnow().isoformat()` → `datetime.datetime.now(datetime.UTC).isoformat()`
   - Line 43: `datetime.datetime.utcnow().isoformat()` → `datetime.datetime.now(datetime.UTC).isoformat()`

3. **`src/doc_extract/api/observability_endpoints.py`** (1 occurrence)
   - Line 74: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`

4. **`src/doc_extract/adapters/sqlite_adapter.py`** (4 occurrences)
   - Line 32: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`
   - Line 33: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`
   - Line 47: `datetime.utcnow().timestamp()` → `datetime.now(UTC).timestamp()`
   - Line 75: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`

5. **`src/doc_extract/adapters/local_storage.py`** (1 occurrence)
   - Line 42: `datetime.utcnow()` → `datetime.now(UTC)`

6. **`src/doc_extract/adapters/gcs_storage.py`** (1 occurrence)
   - Line 75: `datetime.utcnow()` → `datetime.now(UTC)`

7. **`src/doc_extract/adapters/minio_adapter.py`** (1 occurrence)
   - Line 164: `datetime.utcnow()` → `datetime.now(UTC)`

8. **`src/doc_extract/adapters/pubsub_adapter.py`** (3 occurrences)
   - Line 76: `datetime.utcnow().strftime(...)` → `datetime.now(UTC).strftime(...)`
   - Line 96: `datetime.utcnow()` → `datetime.now(UTC)`
   - Line 130: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`

9. **`src/doc_extract/utils/hashing.py`** (1 occurrence)
   - Line 25: `datetime.utcnow().strftime(...)` → `datetime.now(UTC).strftime(...)`

#### Test Code (11 occurrences, 3 files)

10. **`tests/test_ports.py`** (4 occurrences)
    - Lines 27, 39: `datetime.utcnow()` → `datetime.now(UTC)`
    - Lines 56, 67: `datetime.utcnow()` → `datetime.now(UTC)`

11. **`tests/test_adapters_mock.py`** (5 occurrences)
    - Lines 104, 525: `datetime.utcnow()` → `datetime.now(UTC)`
    - Line 807: `datetime.utcnow()` → `datetime.now(UTC)`
    - Lines 830, 894: `datetime.utcnow()` → `datetime.now(UTC)`

12. **`tests/evaluation/run_eval.py`** (1 occurrence)
    - Line 200: `datetime.utcnow().isoformat()` → `datetime.now(UTC).isoformat()`

### Import Updates

For each file, check the existing import style and add `UTC` accordingly:

| File | Current Import | Updated Import |
|------|---------------|----------------|
| `main.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `resilience_endpoints.py` | `import datetime` | No change needed (use `datetime.UTC`) |
| `observability_endpoints.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `sqlite_adapter.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `local_storage.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `gcs_storage.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `minio_adapter.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `pubsub_adapter.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `hashing.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `test_ports.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `test_adapters_mock.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |
| `run_eval.py` | `from datetime import datetime` | `from datetime import datetime, UTC` |

### Domain Model Check

Inspect `src/doc_extract/domain/borrower.py` and any other Pydantic models that use `default_factory=datetime.utcnow`. If found, update to `default_factory=lambda: datetime.now(UTC)`.

## Verification

```bash
# All tests must pass with ZERO deprecation warnings from our code
uv run pytest tests/ -q -W error::DeprecationWarning 2>&1 | head -20

# If the above is too strict (third-party warnings), use:
uv run pytest tests/ -q 2>&1 | grep -c "utcnow"
# Expected: 0

# Confirm no occurrences remain
rg "datetime\.utcnow\(\)" src/ tests/
# Expected: no output
```

## Constraints

- **NO REGRESSION** — All 236 tests must continue to pass
- **Mechanical changes only** — No logic changes, no refactoring beyond the datetime fix
- **Preserve behavior** — `datetime.now(UTC)` returns timezone-aware datetimes; ensure no downstream code relies on naive datetime comparisons. If a comparison breaks, wrap the other side with `.replace(tzinfo=UTC)` or use `datetime.now(UTC).replace(tzinfo=None)` as a last resort (document why).
- **Test the fix** — Run with `-W error::DeprecationWarning` to confirm no warnings leak through from our code
