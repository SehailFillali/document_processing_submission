# System Design: Document Extraction Platform

## Executive Summary

A resilient, event-driven document extraction platform that transforms unstructured loan documents into structured borrower profiles using AI/LLM. Built with hexagonal architecture for testability, extensibility, and production scalability.

**Key metrics:**
- Extract structured borrower profiles from PDFs in < 30 seconds
- 80%+ test coverage with automated quality gates
- Single-command setup (`just setup && just dev`)
- Swap storage, LLM, or database without touching business logic

---

## 1. Architecture Overview

### Hexagonal Architecture (Ports & Adapters)

We use hexagonal architecture to decouple business logic from infrastructure. This means every external dependency (LLM, storage, database) is behind an abstract port, and concrete adapters can be swapped without modifying core logic.

**Why this matters:** A reviewer can read `ports/llm.py` to understand the LLM contract without knowing if we use OpenAI, Gemini, or a local model. Tests run against in-memory adapters with zero external dependencies.

```
                              ┌────────────────────────────────────┐
                              │          Core Domain               │
                              │                                    │
                              │  BorrowerProfile   Provenance      │
                              │  ExtractionResult  ValidationReport│
                              │  DocumentSubmission                │
                              │                                    │
                              └──────────┬─────────────────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            │                            │                            │
    ┌───────▼───────┐          ┌─────────▼─────────┐       ┌────────▼────────┐
    │  LLM Port     │          │  Storage Port     │       │  Database Port  │
    │               │          │                   │       │                 │
    │ extract()     │          │ upload()          │       │ save()          │
    │ validate()    │          │ download()        │       │ get()           │
    │ get_info()    │          │ exists()          │       │ list()          │
    └───────┬───────┘          └─────────┬─────────┘       └────────┬────────┘
            │                            │                          │
  ┌─────────┼─────────┐       ┌──────────┼──────────┐    ┌─────────┼─────────┐
  │         │         │       │          │          │    │         │         │
  ▼         ▼         ▼       ▼          ▼          ▼    ▼         ▼         ▼
OpenAI   Gemini   (Future)  Local     MinIO      GCS   SQLite  Postgres  (BigQuery)

 MVP ←──────────────────────────────────────────────────────────→ Production
```

**ADR Reference:** [ADR 001 - Hexagonal Architecture](docs/adr/001_hexagonal_architecture.md)

---

## 2. Data Pipeline

### Flow: Ingestion → Processing → Storage → Retrieval

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  Client   │───▶│   Ingest     │───▶│  Preprocess  │───▶│   Extract   │───▶│   Validate   │
│  (curl)   │    │  (FastAPI)   │    │  (Node 1)    │    │  (Node 2)   │    │  (Node 3)    │
└──────────┘    └──────┬───────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                       │                                                          │
                       ▼                                                          ▼
                ┌──────────────┐                                          ┌──────────────┐
                │   Storage    │                                          │   Database   │
                │ (Local/MinIO)│                                          │  (SQLite)    │
                └──────────────┘                                          └──────────────┘
```

### Stage Details

| Stage | Responsibility | Failure Mode | Recovery |
|-------|---------------|--------------|----------|
| **Ingest** | Receive file, compute SHA-256 hash, store, create submission | Reject invalid files (413, 415) | Return error immediately |
| **Preprocess** | Validate file exists, check size, verify type | Log error, mark submission failed | Skip to error state |
| **Extract** | Call LLM with document + schema, parse response | Retry with circuit breaker | Fallback to partial extraction |
| **Validate** | Check required fields, confidence threshold, logical consistency | Flag for manual review | Return partial result |

### Idempotency

Every uploaded file is hashed with SHA-256. The same file uploaded twice produces the same hash, enabling:
- Deduplication at ingestion
- Safe retries without data corruption
- Audit trail for processing

---

## 3. AI/LLM Integration

### Strategy: PydanticAI with Structured Output

We use [PydanticAI](https://ai.pydantic.dev/) to enforce structured extraction. The LLM receives a document and a Pydantic schema, and returns validated JSON that matches the schema exactly.

```python
from pydantic_ai import Agent

agent = Agent(
    model="gpt-4o-mini",
    output_type=BorrowerProfile,       # Pydantic schema
    system_prompt=EXTRACTION_PROMPT,    # Domain-specific instructions
)

result = await agent.run(document_text)
# result.data is a validated BorrowerProfile instance
```

### Why This Approach

| Concern | Our Solution |
|---------|-------------|
| **Hallucination** | Pydantic strict validation rejects invented data |
| **Schema drift** | Output type is a Pydantic model — changes break at compile time |
| **Provenance** | Every extracted field includes source_page, verbatim_text, confidence_score |
| **Partial extraction** | Optional fields + MissingField type distinguish "not found" from "not present" |
| **Cost control** | Token tracking + Logfire observability + daily budget alerts |

### Prompt Engineering

The extraction prompt instructs the LLM to:
1. Extract ONLY data explicitly present in the document
2. Never hallucinate or generate missing information
3. Provide confidence scores (0.0-1.0) for each field
4. Note the source page for each extraction
5. Include verbatim text that supports the extraction

**ADR Reference:** [ADR 010 - LLM Provider Selection](docs/adr/010_llm_provider_selection.md)

---

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

---

## 4. Domain Model Design

### BorrowerProfile (Core Entity)

```
BorrowerProfile
├── Identity
│   ├── borrower_id: str
│   ├── name: str
│   └── ssn_last_four: str (validated: ^\d{4}$)
├── Contact
│   ├── address: Address | MissingField
│   │   ├── street, city, state (2-letter), zip_code (5 or 9 digit), country
│   ├── phone: str (validated: ^\d{10}$)
│   └── email: str (validated: ^[^@]+@[^@]+\.[^@]+$)
├── Financial
│   ├── income_history: list[IncomeEntry]
│   │   └── amount (>0), period_start, period_end, source, provenance
│   └── accounts: list[AccountInfo]
│       └── account_number, account_type, institution, balance, provenance
├── Metadata
│   ├── source_documents: list[str]
│   └── extraction_confidence: float (0.0-1.0)
└── Flags
    ├── validation_errors: list[str]
    └── requires_manual_review: bool
```

### Provenance Tracking

Every extracted field carries a `Provenance` object:

```python
class Provenance(BaseModel):
    source_document: str    # Which document
    source_page: int | None # Which page
    verbatim_text: str | None  # Original text
    confidence_score: float # 0.0-1.0
    extraction_timestamp: datetime
```

This enables:
- **Auditability** — trace any field back to its source
- **Quality scoring** — aggregate confidence across fields
- **Manual review** — show reviewers exactly what the LLM saw

**ADR Reference:** [ADR 009 - Domain Models](docs/adr/009_pydantic_domain_models.md)

---

## 5. Processing Pipeline

### 3-Node Pipeline: Preprocess → Extract → Validate

```
                    ┌─────────────────┐
                    │   Preprocess    │
                    │                 │
                    │ • File exists?  │
                    │ • Size OK?     │
                    │ • Type valid?  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Extract      │
                    │                 │
                    │ • Call LLM      │
                    │ • Parse output  │
                    │ • Track tokens  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Validate      │
                    │                 │
                    │ • Required flds │
                    │ • Confidence?   │
                    │ • Consistency?  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Result      │
                    │                 │
                    │ • completed     │
                    │ • partial       │
                    │ • manual_review │
                    │ • failed        │
                    └─────────────────┘
```

### Result States

| Status | Meaning | Action |
|--------|---------|--------|
| `completed` | All validations passed, high confidence | Ready for consumption |
| `partial` | Some fields missing or low confidence | Usable with caveats |
| `manual_review` | Critical issues found | Requires human review |
| `failed` | Pipeline error or complete extraction failure | Retry or investigate |

**ADR Reference:** [ADR 004 - State Machine](docs/adr/004_state_machine.md)

---

## 6. API Design

### RESTful Endpoints

| Method | Endpoint | Purpose | Rate Limit |
|--------|----------|---------|------------|
| GET | `/health` | Health check | 100/min |
| POST | `/api/v1/documents/upload` | Upload document | 10/min |
| POST | `/api/v1/documents/process_uploaded_blob` | Process from blob storage | 10/min |
| GET | `/api/v1/submissions/{id}` | Get submission status | 60/min |
| GET | `/api/v1/submissions` | List submissions | 60/min |
| GET | `/api/v1/blob/health` | Blob storage health | 100/min |
| GET | `/api/v1/observability/cost` | LLM cost stats | 60/min |
| GET | `/api/v1/observability/metrics` | System metrics | 60/min |
| GET | `/api/v1/resilience/circuits` | Circuit breaker status | 60/min |
| GET | `/api/v1/errors/codes` | List error codes | 60/min |

### Versioning

All endpoints are prefixed with `/api/v1/`. This allows introducing breaking changes in `/api/v2/` without affecting existing clients.

### Error Response Format

All errors return a consistent structure:

```json
{
  "error": {
    "code": "E2001",
    "message": "Document processing failed",
    "details": { "stage": "extraction", "reason": "..." },
    "retry_after": null
  }
}
```

**ADR Reference:** [ADR 011 - API Design](docs/adr/011_api_design.md), [ADR 018 - Error Codes](docs/adr/018_error_codes_rate_limiting.md)

---

## 7. Storage Architecture

### Multi-Backend via Adapter Pattern

```
Configuration             Adapter              Backend
─────────────             ───────              ───────
STORAGE_BACKEND=local  →  LocalFileSystem   →  ./uploads/
STORAGE_BACKEND=minio  →  MinIOAdapter      →  MinIO (Docker)
STORAGE_BACKEND=s3     →  MinIOAdapter*     →  AWS S3
                          GCSAdapter        →  Google Cloud Storage

* MinIO client is S3-compatible
```

### URI Scheme Support

| Scheme | Backend | Example |
|--------|---------|---------|
| `file://` | Local filesystem | `file://./uploads/doc.pdf` |
| `minio://` | MinIO (Docker) | `minio://documents/loan.pdf` |
| `s3://` | AWS S3 | `s3://bucket/path/doc.pdf` |
| `gs://` | Google Cloud Storage | `gs://bucket/path/doc.pdf` |

### Database: SQLite (MVP) → PostgreSQL (Production)

SQLite is used for the MVP because:
- Zero configuration
- Single file, easy to inspect
- Sufficient for single-instance deployment

The `DatabasePort` interface allows swapping to PostgreSQL or BigQuery without changing application code.

**ADR Reference:** [ADR 002 - Storage](docs/adr/002_pydantic_domain.md), [ADR 015 - MinIO](docs/adr/015_minio_blob_storage.md)

---

## 8. Error Handling Strategy

### Structured Error Codes

Every error has a machine-readable code for programmatic handling:

| Category | Range | Example |
|----------|-------|---------|
| Validation | `VAL_*` | `VAL_FILE_TOO_LARGE` |
| Processing | `PROC_*` | `PROC_EXTRACTION_FAILED` |
| Storage | `STORAGE_*` | `STORAGE_FILE_NOT_FOUND` |
| LLM | `LLM_*` | `LLM_RATE_LIMITED` |
| Rate Limiting | `RATE_*` | `RATE_LIMIT_EXCEEDED` |
| Internal | `INTERNAL_*` | `INTERNAL_DATABASE_ERROR` |

### Error Handling by Layer

| Layer | Strategy | Example |
|-------|----------|---------|
| **API** | Validate input, return 4xx | File too large → 413 |
| **Processing** | Retry with backoff, circuit break | LLM timeout → retry 3x |
| **Extraction** | Partial success, flag for review | Missing name → partial result |
| **Storage** | Retry, fallback to local | S3 down → queue for retry |

### Circuit Breaker Pattern

External service calls (LLM, storage) are protected by circuit breakers:

```
Normal ──[5 failures]──▶ Open ──[30s timeout]──▶ Half-Open ──[3 successes]──▶ Closed
                          │                        │
                          │                        │ [failure]
                          └────────────────────────┘
```

**ADR Reference:** [ADR 007 - Error Handling](docs/adr/007_error_handling.md), [ADR 016 - Circuit Breaker](docs/adr/016_circuit_breaker_resilience.md)

---

## 9. Observability

### Logfire Integration

We use Logfire (from the Pydantic team) for:

| Feature | Purpose |
|---------|---------|
| **Request tracing** | End-to-end trace from upload to result |
| **LLM cost tracking** | Token usage + cost per request |
| **Budget alerts** | Warn at 80% daily budget, block at 100% |
| **Performance metrics** | P95 latency, error rates |

### Cost Tracking

```
POST /api/v1/documents/upload
  └── LLM call: 1,200 input tokens + 800 output tokens
      └── Cost: $0.0003
          └── Daily total: $12.50 / $100.00 budget (12.5%)
```

### Endpoints

- `GET /api/v1/observability/cost` — Current cost summary
- `GET /api/v1/observability/metrics` — System-wide metrics
- `GET /api/v1/resilience/circuits` — Circuit breaker health

**ADR Reference:** [ADR 017 - Logfire](docs/adr/017_logfire_observability.md)

---

## 10. Scaling Considerations

### Current: Single Instance (MVP)

```
Client → FastAPI (1 instance) → SQLite → Local Storage
```

Handles: ~100 documents/day

### 10x Scale: 1,000 documents/day

```
Client → Cloud Run (auto-scale) → PostgreSQL → GCS
              └── Pub/Sub for async processing
```

Changes needed:
- Swap `LocalFileSystemAdapter` → `GCSStorageAdapter`
- Swap `SQLiteAdapter` → `PostgreSQLAdapter`
- Add Pub/Sub queue adapter
- Deploy to Cloud Run

**No application code changes** — only adapter configuration.

### 100x Scale: 100,000 documents/day

```
Client → Load Balancer → Cloud Run (N instances)
              │
              └── Pub/Sub → Worker Pool (M instances)
                      │
                      ├── GCS (document storage)
                      ├── BigQuery (analytics)
                      └── Redis (caching + dedup)
```

Additional changes:
- Add BigQuery adapter for analytics
- Redis for deduplication cache
- Worker pool for async extraction
- Horizontal scaling of API and workers independently

**ADR Reference:** [ADR 006 - Scaling](docs/adr/006_scaling.md)

---

## 11. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| **PII in documents** | No PII stored in logs; SSN stored as last 4 digits only |
| **API abuse** | Rate limiting (10/min upload, 60/min query) |
| **File uploads** | Size limit (50MB), type validation, SHA-256 hashing |
| **LLM data privacy** | API key auth; no document content in logs |
| **Infrastructure** | Non-root Docker user, minimal base image |
| **Secrets** | Environment variables, never in code |

---

## 12. Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Package Manager** | uv | 10-100x faster than pip |
| **Task Runner** | just | Self-documenting, shell-agnostic |
| **API** | FastAPI | Async-native, auto-docs, Pydantic integration |
| **Validation** | Pydantic v2 | Strict mode, JSON schema generation |
| **LLM Agent** | PydanticAI | Structured output with type safety |
| **LLM Provider** | OpenAI gpt-4o-mini | Best PydanticAI integration, reviewer-friendly |
| **Database** | SQLite (MVP) | Zero config, portable |
| **Storage** | Local + MinIO | S3-compatible, easy Docker setup |
| **Observability** | Logfire | Pydantic ecosystem, LLM cost tracking |
| **Resilience** | Custom circuit breaker | No external dependency |
| **IaC** | Terraform | Industry standard |
| **CI/CD** | GitHub Actions | Free tier, tight GitHub integration |
| **Container** | Docker + Compose | Reproducible environments |

---

## 13. Architecture Decision Records

| ADR | Decision | Alternatives Considered |
|-----|----------|------------------------|
| [001](docs/adr/001_hexagonal_architecture.md) | Hexagonal Architecture | Layered, Clean, Onion |
| [002](docs/adr/002_pydantic_domain.md) | SQLite for MVP storage | PostgreSQL, DynamoDB |
| [003](docs/adr/003_llm_provider.md) | PydanticAI + Gemini/OpenAI | LangChain, direct API |
| [004](docs/adr/004_state_machine.md) | Processing pipeline | Celery, simple functions |
| [005](docs/adr/005_event_driven.md) | Event-driven design | Synchronous, polling |
| [006](docs/adr/006_scaling.md) | Cloud Run + GCS | ECS, Kubernetes |
| [007](docs/adr/007_error_handling.md) | Structured error codes | HTTP-only errors |
| [008](docs/adr/008_project_tooling.md) | uv + just | pip + Make, Poetry |
| [009](docs/adr/009_pydantic_domain_models.md) | Pydantic v2 strict | dataclasses, attrs |
| [010](docs/adr/010_llm_provider_selection.md) | OpenAI default + Gemini | Claude, VertexAI |
| [011](docs/adr/011_api_design.md) | FastAPI | Flask, Django REST |
| [012](docs/adr/012_evaluation_framework.md) | Golden set evaluation | Manual review, synthetic |
| [013](docs/adr/013_cicd_pipeline.md) | GitHub Actions | Jenkins, GitLab CI |
| [014](docs/adr/014_test_strategy.md) | pytest + 80% coverage | unittest, Hypothesis |
| [015](docs/adr/015_minio_blob_storage.md) | MinIO for dev storage | Direct S3, local only |
| [016](docs/adr/016_circuit_breaker_resilience.md) | Custom circuit breaker | pybreaker, Tenacity |
| [017](docs/adr/017_logfire_observability.md) | Logfire observability | DataDog, Prometheus |
| [018](docs/adr/018_error_codes_rate_limiting.md) | Enum error codes + rate limiting | API Gateway, custom |
| [024](docs/adr/024_native_llm_pdf_ingestion.md) | Native LLM PDF ingestion | pymupdf, pdfplumber, docling, marker, cloud OCR |

---

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

---

## 15. What I Would Do Next (Given More Time)

1. **Authentication** — API key or JWT-based auth for multi-tenant support
2. **Async processing** — Pub/Sub queue with background workers for long extractions
3. **Document chunking** — Split 200+ page documents into chunks for parallel extraction
4. **Multi-document correlation** — Cross-reference data across multiple documents for the same borrower
5. **Schema registry** — Version extraction schemas to handle format changes gracefully
6. **Canary deployments** — Route 5% of traffic to new LLM prompts before full rollout
7. **Data retention** — Auto-delete PII after configurable period
8. **Webhook notifications** — Notify clients when extraction completes instead of polling
