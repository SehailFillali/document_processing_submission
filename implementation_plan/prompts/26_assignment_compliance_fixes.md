# Prompt 26: Assignment Compliance Fixes

## Status
[COMPLETED]

## Context

A line-by-line audit of the assignment requirements (`assignment.md`) against our deliverables revealed 6 gaps — 2 critical, 2 required, 1 high, and 1 medium. This prompt addresses all of them in priority order. Every fix is traced back to the specific assignment requirement it satisfies.

**Audit source:** The assignment states:

> *"Analyze the documents and produce a structured record for each borrower that includes extracted PII like their name, address, full income history, and associated account/loan numbers, with a clear reference to the original document(s) from which the information was sourced"*

And Deliverable 1 (System Design Document) must include:

> *"Approach for handling document format variability"*
> *"Key technical trade-offs and reasoning"*

---

## Fix 1 (CRITICAL): Native PDF Ingestion in OpenAI Adapter

### Problem

The OpenAI adapter at `adapters/openai_adapter.py:57-59` sends:

```python
"content": f"Extract structured data from this document: {request.document_url}",
```

This sends a literal string like `"file://uuid/paystub.pdf"` as the user message. The OpenAI Chat Completions API **cannot resolve local file paths**. The LLM receives a path string and would hallucinate every field.

ADR 024 documents the deliberate decision to use **native LLM PDF ingestion** (all major models accept PDF files directly). The architecture is correct — the implementation is incomplete.

### Assignment requirement violated

> *"Extraction logic using AI/LLM tooling"* — the extraction logic does not actually process documents.

### Solution

Use the OpenAI Chat Completions API's native PDF file input. PDFs are sent as base64-encoded `file` content blocks. The LLM extracts text and renders page images internally.

**Reference:** https://platform.openai.com/docs/guides/pdf-files?api-mode=chat

### Files to modify

#### 1.1 `src/doc_extract/ports/llm.py`

Add `document_content` field to `ExtractionRequest`:

```python
@dataclass
class ExtractionRequest:
    """Request for LLM extraction."""

    document_url: str
    document_type: str
    output_schema: type[BaseModel]
    system_prompt: str | None = None
    validation_rules: list | None = None
    document_content: bytes | None = None  # NEW: raw file bytes for native ingestion
```

**Backward compatibility:** Defaults to `None`. All existing tests construct `ExtractionRequest` without this field and will continue to work.

#### 1.2 `src/doc_extract/adapters/openai_adapter.py`

Replace the simple string user message with a multipart content array. When `document_content` is provided, send the PDF as a base64-encoded file content block:

```python
import base64

# Build user message content
user_content = []

if request.document_content:
    # Native PDF ingestion via Chat Completions file content block
    b64_data = base64.b64encode(request.document_content).decode()
    filename = request.document_url.split("/")[-1] if "/" in request.document_url else "document.pdf"
    user_content.append({
        "type": "file",
        "file": {
            "filename": filename,
            "file_data": f"data:application/pdf;base64,{b64_data}",
        },
    })
    user_content.append({
        "type": "text",
        "text": "Extract all structured borrower data from this document.",
    })
else:
    # Fallback: send document_url as text (for testing / non-file inputs)
    user_content = f"Extract structured data from this document: {request.document_url}"

response = await client.chat.completions.create(
    model=self.model_name,
    messages=[
        {"role": "system", "content": request.system_prompt or SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": request.output_schema.__name__,
            "schema": schema_json,
        },
    },
)
```

**Key detail:** The `file_data` value must be a data URI: `data:application/pdf;base64,{base64_content}`. The `filename` field is required by the OpenAI API.

#### 1.3 `src/doc_extract/services/processing.py`

Currently line 56 downloads the file but **discards the return value**:

```python
await self.storage.download(storage_path)  # return value ignored
```

Fix: capture the bytes and pass them to the LLM:

```python
# Download document content
file_bytes = await self.storage.download(storage_path)

# ... later, when building the ExtractionRequest:
request = ExtractionRequest(
    document_url=document_url,
    document_type="loan_application",
    output_schema=BorrowerProfile,
    system_prompt=system_prompt,
    document_content=file_bytes,  # NEW: pass actual file content
)
```

Also update the critic call to pass file bytes:

```python
critique_result = await self.critic.critique(
    document_url=document_url,
    extracted_data=extracted_data,
    feedback_history=feedback_history if feedback_history else None,
    document_content=file_bytes,  # NEW
)
```

#### 1.4 `src/doc_extract/agents/critic_agent.py`

Add `document_content: bytes | None = None` parameter to the `critique()` method. When provided, send the PDF as a base64 file block in the critic's user message so it can **actually verify** extracted fields against the source document:

```python
async def critique(
    self,
    document_url: str,
    extracted_data: dict,
    feedback_history: list[str] | None = None,
    document_content: bytes | None = None,  # NEW
) -> CritiqueResult:
```

In the try block, build the messages with file content when available:

```python
user_content = []

if document_content:
    import base64
    b64_data = base64.b64encode(document_content).decode()
    filename = document_url.split("/")[-1] if "/" in document_url else "document.pdf"
    user_content.append({
        "type": "file",
        "file": {
            "filename": filename,
            "file_data": f"data:application/pdf;base64,{b64_data}",
        },
    })

user_content.append({
    "type": "text",
    "text": (
        f"Extracted data to verify:\n"
        f"{json.dumps(extracted_data, indent=2, default=str)}"
        f"{feedback_context}"
    ),
})

response = await client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": CRITIQUE_PROMPT},
        {"role": "user", "content": user_content},
    ],
    response_format={...},
)
```

**Fallback behavior:** If `document_content` is `None`, fall back to sending `document_url` as text in the user message (existing behavior). This keeps all existing tests working since they mock the LLM calls and don't provide file bytes.

### Test impact

- All existing tests mock `OpenAIAdapter` or `AsyncOpenAI` — they never make real API calls and won't be affected.
- Tests that construct `ExtractionRequest(document_url="file://test.pdf", ...)` continue to work because `document_content` defaults to `None`.
- Tests that call `critic.critique(document_url=..., extracted_data=..., ...)` continue to work because `document_content` defaults to `None`.
- **No new tests required** for this fix since the LLM calls are always mocked in the test suite. The fix ensures real invocations (demo, production) send actual content.

---

## Fix 2 (REQUIRED): SYSTEM_DESIGN.md — "Document Format Handling" Section

### Problem

SYSTEM_DESIGN.md has no section addressing how variable document formats are handled. The assignment specifies the corpus has *"variable formatting, mixed file types, and structured data embedded within unstructured text"* and requires *"Approach for handling document format variability"* in the System Design Document.

The rationale exists in ADR 024 (native LLM PDF ingestion) and ADR 019 (Excel preprocessing), but the main deliverable document doesn't surface it.

### Assignment requirement violated

> Deliverable 1, item 4: *"Approach for handling document format variability"*

### Solution

**File:** `SYSTEM_DESIGN.md`

Insert a new section after `## 3. AI/LLM Integration` (after line 128). Title: `## 3.5 Document Format Handling`. Content:

```markdown
## 3.5 Document Format Handling

### Strategy: Native Multimodal LLM Ingestion

The provided document corpus contains variable formatting and mixed file types — text-searchable PDFs, scanned PDFs, financial forms (W2, 1040), and tabular documents (bank statements, closing disclosures). Rather than building a local text extraction pipeline, we send documents directly to multimodal LLMs that process PDFs natively.

| Format Challenge | How It's Handled |
|-----------------|-----------------|
| **Text-searchable PDFs** | LLM extracts text directly from the PDF |
| **Scanned/image PDFs** | LLM vision capabilities read page images — no separate OCR pipeline |
| **Forms and tables** (W2 boxes, 1040 line items) | LLM interprets spatial layout, preserving table structure that text extraction would destroy |
| **Mixed content** (text + charts + signatures) | Multimodal processing handles all content types in a single pass |
| **Excel financial statements** | Future: 8-step preprocessing pipeline converts to clean PDF via LibreOffice (ADR 019) |

### Why Not Local Text Extraction?

Local PDF parsing (pymupdf, pdfplumber, pypdf) introduces significant complexity:
- Cannot handle scanned PDFs without a separate OCR pipeline
- Destroys table structure and spatial layout critical for loan forms
- Requires reading order reconstruction for multi-column documents
- Adds weeks of engineering for a capability the LLM already has

For the MVP volume (<100 docs/day), the token cost of native PDF ingestion (~$0.05 per 10-page document with gpt-4o-mini) is negligible compared to the engineering cost of a robust parsing pipeline.

### Future: Hybrid Approach at Scale

At >1,000 docs/day, token cost becomes significant. ADR 024 documents a hybrid strategy: use local text extraction (pymupdf/docling) for text-heavy documents, falling back to LLM vision for scanned content or complex layouts. This reduces token cost by 60-80% while maintaining extraction quality.

**ADR Reference:** [ADR 024 - Native LLM PDF Ingestion](docs/adr/024_native_llm_pdf_ingestion.md), [ADR 019 - Excel Preprocessing](docs/adr/019_excel_preprocessing.md)
```

---

## Fix 3 (REQUIRED): SYSTEM_DESIGN.md — "Key Technical Trade-offs" Section

### Problem

SYSTEM_DESIGN.md has no consolidated trade-off section. Individual ADRs contain trade-off analysis, but the main design document — which is the graded deliverable — doesn't surface it.

### Assignment requirement violated

> Deliverable 1, item 6: *"Key technical trade-offs and reasoning"*

### Solution

**File:** `SYSTEM_DESIGN.md`

Insert a new section before `## 14. What I Would Do Next` (before line 488). Title: `## 14. Key Technical Trade-offs`. Renumber "What I Would Do Next" to `## 15`.

```markdown
## 14. Key Technical Trade-offs

Every architectural decision involves trade-offs. This section consolidates the major ones and explains why we landed where we did.

| Decision | What We Traded Away | Why It's Worth It | ADR |
|----------|--------------------|--------------------|-----|
| **Native LLM PDF ingestion** over local text extraction | Higher token cost per document (~$0.05/doc) | Eliminates entire PDF parsing subsystem. LLM handles scanned docs, tables, and forms natively. Zero preprocessing infrastructure. | [024](docs/adr/024_native_llm_pdf_ingestion.md) |
| **SQLite** over PostgreSQL for MVP | Concurrency, multi-instance deployment | Zero configuration, single file, portable. `DatabasePort` interface allows swap to Postgres without code changes. | [002](docs/adr/002_pydantic_domain.md) |
| **Synchronous processing** over async queue | Throughput at scale | MVP handles <100 docs/day. Pub/Sub adapter is implemented and ready for the 10x phase. Simplicity reduces debugging surface. | [005](docs/adr/005_event_driven.md) |
| **Custom circuit breaker** over pybreaker/Tenacity | Library maintenance savings | pybreaker lacks async support. Custom implementation is 202 lines, fully tested, and gives complete control over state transitions and the health API. | [016](docs/adr/016_circuit_breaker_resilience.md) |
| **OpenAI gpt-4o-mini** as default over Gemini/Claude | Provider lock-in risk | Best structured output support via `response_format: json_schema`. Lowest cost for quality. `LLMPort` abstraction mitigates lock-in — Gemini adapter also implemented. | [010](docs/adr/010_llm_provider_selection.md) |
| **In-memory submission storage** over database-backed | Data lost on restart | `SQLiteAdapter` is implemented and tested (191 lines, full CRUD). Wiring deferred to focus engineering time on extraction quality, resilience, and observability. Acceptable for demo. | — |
| **Hexagonal architecture** over simpler layered | More boilerplate (ports + adapters) | Enables parallel team development — engineers add adapters without touching core logic. Swappable infrastructure for scaling tiers. Worth the upfront cost for a system designed to grow. | [001](docs/adr/001_hexagonal_architecture.md) |

### Design Principles Behind These Choices

1. **Defer complexity until forced.** We don't build a PDF parsing pipeline when the LLM handles PDFs natively. We don't deploy PostgreSQL when SQLite handles the MVP.

2. **Invest in interfaces early.** Ports cost little to define but make every future swap frictionless. The `LLMPort`, `BlobStoragePort`, `DatabasePort`, and `QueuePort` are the highest-leverage code in the system.

3. **Production patterns at MVP scale.** Circuit breaker, rate limiting, structured error codes, and Prometheus metrics add ~600 lines of code but are the difference between a demo and a deployable system.
```

---

## Fix 4 (HIGH): Per-Field Provenance on BorrowerProfile

### Problem

The assignment requires *"a clear reference to the original document(s) from which the information was sourced."* The `IncomeEntry` and `AccountInfo` models carry `Provenance` objects, but `name` and `address` do not. A reviewer would rightfully ask: "Which document did you get the borrower's name from?"

### Assignment requirement violated

> *"...with a clear reference to the original document(s) from which the information was sourced"*

### Solution

**File:** `src/doc_extract/domain/borrower.py`

Add provenance fields for name and address to `BorrowerProfile`:

```python
class BorrowerProfile(DomainModel):
    """Complete borrower profile extracted from documents."""

    # Identity - made optional for partial extraction
    borrower_id: str | None = Field(None, description="Unique borrower identifier")
    name: str | None = Field(None, min_length=1, description="Borrower full name")
    name_provenance: Provenance | None = Field(
        None, description="Source document reference for borrower name"
    )
    ssn_last_four: str | None = Field(
        None, pattern=r"^\d{4}$", description="Last 4 digits of SSN for verification"
    )

    # Contact - made optional
    address: Address | MissingField | None = Field(None)
    address_provenance: Provenance | None = Field(
        None, description="Source document reference for address"
    )
    # ... rest unchanged
```

Update `calculate_overall_confidence()` to include the new provenance fields:

```python
def calculate_overall_confidence(self) -> float:
    """Calculate weighted average confidence from all provenance fields."""
    confidences = []

    if self.name_provenance:
        confidences.append(self.name_provenance.confidence_score)

    if self.address_provenance:
        confidences.append(self.address_provenance.confidence_score)

    for income in self.income_history:
        confidences.append(income.provenance.confidence_score)

    for account in self.accounts:
        confidences.append(account.provenance.confidence_score)

    if not confidences:
        return 0.0

    return sum(confidences) / len(confidences)
```

**File:** `src/doc_extract/adapters/openai_adapter.py` and `src/doc_extract/adapters/gemini_adapter.py`

Update `SYSTEM_PROMPT` in both files. Add after the existing extraction instructions:

```
For the borrower's name and address, also provide:
- The source document name
- The page number where it was found
- The verbatim text containing the name/address
- Your confidence score (0.0 to 1.0)
```

### Test impact

- `name_provenance` and `address_provenance` default to `None` — all existing `BorrowerProfile(...)` constructions in tests will continue to work.
- Tests that check `calculate_overall_confidence()` may return slightly different values if they now construct profiles with these fields populated. Check `test_domain.py` and `test_edge_cases.py` for any assertions on confidence calculation. If tests construct profiles without provenance, the confidence calculation is unchanged (no new `confidences` entries when fields are `None`).

---

## Fix 5 (MEDIUM): README Architecture Summary Expansion

### Problem

The assignment requires *"Summary of architectural and implementation decisions"* in the README. The current "Architecture Highlights" section (lines 378-385) lists what was chosen but not why.

### Assignment requirement violated

> Deliverable 3, item 2: *"Summary of architectural and implementation decisions"*

### Solution

**File:** `README.md`

Replace the current "Architecture Highlights" section (lines 378-385) with:

```markdown
## Architecture Highlights

- **Hexagonal Architecture** — Every external dependency (LLM, storage, database, queue) is behind an abstract port. Adapters can be swapped without touching business logic. This enables parallel team development and frictionless infrastructure changes when scaling. See [ADR 001](docs/adr/001_hexagonal_architecture.md).

- **PydanticAI + Structured Output** — LLM responses are constrained to exact Pydantic schemas via `response_format: json_schema`. This prevents hallucinated field names and types, and ensures every extraction result is type-safe and validated. See [ADR 003](docs/adr/003_llm_provider.md).

- **Native PDF Ingestion** — Documents are sent directly to multimodal LLMs that process PDFs natively, preserving table structure, forms, and spatial layout. This eliminates the need for a local PDF parsing pipeline. See [ADR 024](docs/adr/024_native_llm_pdf_ingestion.md).

- **Self-Correction Loop** — Extractions are verified by a Critic Agent (a second LLM call). If the QA score falls below 80%, feedback is injected into the extraction prompt and the extraction is retried (up to 2 times). The best result across all attempts is returned. See [ADR 020](docs/adr/020_multi_critic_panel.md).

- **Production Resilience** — Circuit breaker (prevents cascade failures), token-bucket rate limiting (per-client, multi-window), 30 structured error codes, and Prometheus metrics (11 custom metrics). These are not "nice-to-haves" — they're the minimum for a deployable system. See [ADR 016](docs/adr/016_circuit_breaker_resilience.md), [ADR 018](docs/adr/018_error_codes_rate_limiting.md).

- **Multi-Storage / Multi-LLM** — Local, MinIO, S3, GCS storage via adapter pattern. OpenAI and Gemini LLM providers via `LLMPort`. Configuration-driven backend selection — changing `STORAGE_BACKEND=minio` or swapping LLM providers requires zero code changes. See [ADR 010](docs/adr/010_llm_provider_selection.md), [ADR 015](docs/adr/015_minio_blob_storage.md).

See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for full architecture details and [docs/adr/](docs/adr/) for all 24 Architecture Decision Records.
```

---

## Fix 6 (LOW): Prerequisites and .gitignore

### 6.1 Add `just` to README Prerequisites

**File:** `README.md`

Update the Prerequisites section (lines 6-9) to include `just`:

```markdown
## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- [just](https://github.com/casey/just) (command runner — used for all project tasks)
- Docker & Docker Compose (for containerized services)
```

### 6.2 Add sample docs to .gitignore

**File:** `.gitignore`

Add at the end:

```gitignore
# Assignment sample documents (not part of the project)
Engineer take home docs 2026/
*.zip
```

This prevents accidental commit of the 16 sample PDFs and the original zip file.

---

## Verification

```bash
# All existing tests must still pass
uv run pytest tests/ -q
# Expected: 236 passed (or more)

# Verify ExtractionRequest backward compatibility
uv run python -c "from doc_extract.ports.llm import ExtractionRequest; r = ExtractionRequest(document_url='test', document_type='loan', output_schema=type('M', (), {})); print('OK')"

# Verify BorrowerProfile backward compatibility
uv run python -c "from doc_extract.domain.borrower import BorrowerProfile; p = BorrowerProfile(); print('OK')"

# Verify SYSTEM_DESIGN.md has all 7 required sections
grep -c "Document Format" SYSTEM_DESIGN.md   # Expected: >= 1
grep -c "Trade-off" SYSTEM_DESIGN.md          # Expected: >= 1

# Verify .gitignore
grep "Engineer take home" .gitignore          # Expected: match
```

## Constraints

- **NO REGRESSION** — All 236 existing tests must continue to pass
- **Backward compatible** — `document_content` and provenance fields default to `None`; no existing code path breaks
- **No new dependencies** — `base64` is a stdlib module
- **SYSTEM_DESIGN.md and README are deliverables** — they must stand on their own without requiring a reviewer to read every ADR
- **Do not remove `document_url`** — it remains for metadata, logging, and fallback behavior
