# Prompt 21: Code Quality Fixes - Type Errors and API Consistency

## Status
[PARTIALLY_IMPLEMENTED] - some type issues remain

## Context

Static analysis (LSP / pyright) reveals type errors across multiple files. These must be fixed before the assignment is submitted. A "Head of Engineering" codebase cannot ship with type errors visible in any editor.

## Objective

Fix all type errors while maintaining backward compatibility with existing tests and API behavior. **NO REGRESSION** on existing functionality.

## Issues to Fix

### Issue 1: `services/graph.py` — Pydantic Graph API Misuse (CRITICAL)

**Root Cause:** The `BaseNode.run()` method signature uses `ctx` as its second parameter (not `state`). Each node also passes `state=` as a keyword argument to the next node's constructor, but `BaseNode` dataclasses don't accept a `state` keyword in `__init__` — that's just a regular field we defined. The Graph also requires all nodes to share the same state type, but we use three different state types (`PreprocessState`, `ExtractState`, `ValidateState`).

**Errors:**
- Line 82, 156, 263: `run()` overrides `BaseNode` incompatibly — parameter named `state` should be `ctx`
- Line 131, 197: `No parameter named "state"` when constructing next node
- Line 133, 199: `No parameter named "document_paths"` when constructing next node
- Line 405: Graph constructor rejects mixed state types
- Line 417: `PreprocessNode` not assignable to `BaseNode[ExtractState]`

**Fix Strategy — Choose ONE:**

**Option A (Recommended): Replace Pydantic Graph with simple async pipeline**

Pydantic Graph's type system is too rigid for our 3-state pipeline. Replace with a simple, type-safe async pipeline that preserves the same Preprocess → Extract → Validate flow. This is pragmatic and honest.

```python
"""Document processing pipeline.

3-node pipeline: Preprocess → Extract → Validate
Replaces Pydantic Graph with simple async functions for type safety.

ADR Reference: docs/adr/004_state_machine.md
"""

from dataclasses import dataclass
from doc_extract.core.logging import logger

@dataclass
class PipelineResult:
    submission_id: str
    status: str  # completed | partial | failed | manual_review
    borrower_profile: dict | None = None
    validation_report: dict | None = None
    processing_time_seconds: float = 0.0
    token_usage: dict | None = None
    errors: list[dict] | None = None

async def preprocess(submission_id: str, document_paths: list[str]) -> tuple[bool, list[str]]:
    """Node 1: Validate documents exist and are processable."""
    # ... existing PreprocessNode.run() logic, return (ok, errors)

async def extract(submission_id: str, document_paths: list[str]) -> tuple[dict, float, dict, float]:
    """Node 2: LLM extraction."""
    # ... existing ExtractNode.run() logic, return (raw_extraction, confidence, token_usage, time)

async def validate(submission_id: str, raw_extraction: dict, confidence: float) -> PipelineResult:
    """Node 3: Validate and produce final result."""
    # ... existing ValidateNode.run() logic, return PipelineResult

async def process_document(submission_id: str, document_paths: list[str]) -> dict:
    """Run the full pipeline."""
    ok, errors = await preprocess(submission_id, document_paths)
    if not ok:
        return {"submission_id": submission_id, "status": "failed", "errors": errors}
    
    raw, confidence, tokens, time_s = await extract(submission_id, document_paths)
    result = await validate(submission_id, raw, confidence)
    result.processing_time_seconds = time_s
    result.token_usage = tokens
    return result.__dict__
```

**Option B: Fix Pydantic Graph usage to match actual API**

If keeping Pydantic Graph, unify to a single shared state type and fix `run()` signatures to use `ctx`. This is more complex and may not match the library's actual API well.

---

### Issue 2: `api/main.py` — `DocumentMetadata` Missing `page_count` (MEDIUM)

**Error (line 86):** `Argument missing for parameter "page_count"`

**Root Cause:** `DocumentMetadata` in `submission.py` has `page_count: int | None = Field(None, ...)` which has a default. But this error suggests the LSP sees it as required.

**Fix:** This may be a false positive due to `strict=True` on a parent model. Verify by checking if `DocumentMetadata` inherits from `DomainModel`. If so, the strict config may be inherited.

Actually looking at the code: `DocumentMetadata(BaseModel)` — it inherits from plain `BaseModel`, not `DomainModel`. The `page_count` field has a default of `None`. This is likely a pyright inference issue with keyword-only arguments.

**Fix:** Explicitly pass `page_count=None` to the constructor calls in `main.py:115` and `blob_endpoints.py:99`:

```python
doc_metadata = DocumentMetadata(
    document_id=document_id,
    file_hash=file_hash_str,
    file_name=file.filename,
    file_size=len(content),
    mime_type=file.content_type or "application/octet-stream",
    document_type=DocumentType(document_type),
    page_count=None,  # Add explicitly
)
```

---

### Issue 3: `api/main.py` — `borrower_profile_id` Type Mismatch (MEDIUM)

**Error (line 151):** `Argument of type "str | None" cannot be assigned to parameter "borrower_profile" of type "dict | None"`

**Root Cause:** `DocumentSubmission.borrower_profile_id` is `str | None`, but `QueryResponse.borrower_profile` is `dict | None`. At line 180, we pass `submission.borrower_profile_id` (str) where a dict is expected.

**Fix:** Change `DocumentSubmission.borrower_profile_id` from `str | None` to `dict | None` to store the actual profile data. Update `submission.py`:

```python
class DocumentSubmission(BaseModel):
    ...
    borrower_profile_id: dict | None = None  # Was str | None
```

Or rename the field to `borrower_profile` for clarity and update all references.

---

### Issue 4: `api/blob_endpoints.py` — `LocalFileSystemAdapter` has no `.client` (LOW)

**Error (line 166-167):** `Cannot access attribute "client" for class "LocalFileSystemAdapter"`

**Root Cause:** The `/blob/health` endpoint does `storage.client.list_buckets()`, but `get_storage_adapter()` may return `LocalFileSystemAdapter` which has no `.client` attribute (that's a MinIO-specific attribute).

**Fix:** Use `hasattr` check that also verifies the method exists, or better yet, add a `health_check()` method to the `BlobStoragePort` interface:

```python
@router.get("/blob/health")
async def blob_storage_health():
    """Check blob storage connectivity."""
    try:
        storage = get_storage_adapter()
        # Use duck typing safely
        if hasattr(storage, "client") and hasattr(storage.client, "list_buckets"):
            storage.client.list_buckets()
            return {"status": "healthy", "backend": settings.storage_backend}
        # For local storage, just check the directory exists
        if hasattr(storage, "base_path"):
            return {"status": "healthy", "backend": "local"}
        return {"status": "unknown", "backend": settings.storage_backend}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

---

### Issue 5: `adapters/gemini_adapter.py` — Type Safety Issues (LOW)

**Error (line 39):** `os.environ["GEMINI_API_KEY"] = self.api_key` — `self.api_key` is `str | None`, but `os.environ[]` requires `str`.

**Fix:**
```python
def __init__(self, api_key: str | None = None):
    self.api_key = api_key or settings.gemini_api_key or ""
    if self.api_key:
        os.environ["GEMINI_API_KEY"] = self.api_key
```

**Error (line 63):** `result.data` — pyright doesn't recognize `.data` on `AgentRunResult`.

**Fix:** This is a PydanticAI API issue. The attribute exists at runtime but pyright doesn't see it. Add a type ignore comment or use `getattr`:
```python
extracted = getattr(result, "data", result)  # type: ignore[attr-defined]
```

**Error (line 87):** `await Agent(...)` — Agent constructor is not awaitable.

**Fix:** The `validate_connection` method should call `agent.run()` instead of awaiting the constructor:
```python
async def validate_connection(self) -> bool:
    try:
        from pydantic_ai import Agent
        class HealthCheck(BaseModel):
            status: str
        agent = Agent(model=self.model_name, output_type=HealthCheck)
        result = await agent.run("Return status: ok")
        return True
    except Exception as e:
        logger.error(f"Connection validation failed: {e}")
        return False
```

---

### Issue 6: `core/config.py` — Settings Instantiation Without Required Fields (LOW)

**Error (line 50):** `Arguments missing for parameters "gemini_api_key", "openai_api_key"`

**Root Cause:** Both fields have `None` as default via `Field(None, ...)`. This should work. The issue is that pyright sees `str | None = Field(None)` but may infer the `Field()` call differently.

**Fix:** Use explicit `default=None`:
```python
gemini_api_key: str | None = Field(default=None, description="Gemini API key")
openai_api_key: str | None = Field(default=None, description="OpenAI API key")
```

---

## Execution Order

1. **Fix Issue 1** (graph.py) — Critical, most complex
2. **Fix Issue 3** (submission.py type mismatch) — Affects API correctness
3. **Fix Issue 2** (page_count) — Quick fix in two files
4. **Fix Issue 5** (gemini_adapter.py) — Type safety
5. **Fix Issue 6** (config.py) — Type inference
6. **Fix Issue 4** (blob health) — Minor

## Verification

After all fixes:
```bash
# Run tests — must all pass
just test

# Run type checker
pyright src/doc_extract/

# Verify API still works
just dev
curl http://localhost:8000/health
```

## Constraints
- **NO REGRESSION** — All existing tests must pass
- **NO new dependencies** — Fix with existing libraries
- **Preserve API contracts** — Response shapes must not change
- **Update ADR 004** if replacing Pydantic Graph (Option A)
