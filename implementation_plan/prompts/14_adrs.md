# Prompt 14: ADRs - Architecture Decision Records

## Status
[COMPLETED]

## Context
Creating all 7 required ADR documents with detailed comparison tables and defense notes.

## Objective
Write comprehensive ADRs for every major architectural decision.

## Requirements

Create 7 ADR files in `docs/adr/`:

### 1. ADR 001: Hexagonal Architecture
File: `docs/adr/001_hexagonal_architecture.md`

```markdown
# ADR 001: Hexagonal Architecture (Ports & Adapters)

## Status
Accepted

## Context
We need an architectural pattern that decouples business logic from infrastructure concerns. This enables testing, swapping implementations, and maintaining clean separation of concerns.

## Decision
We will use Hexagonal Architecture (Ports & Adapters) pattern.

## Comparison

| Pattern | Pros | Cons | Best For | Verdict |
|---------|------|------|----------|---------|
| **Hexagonal (Ports & Adapters)** | Clean separation, testable, swappable implementations, infrastructure agnostic | More boilerplate, learning curve | Production systems, microservices | **CHOSEN** |
| **Layered (N-tier)** | Simple, widely understood | Business logic mixed with infrastructure, hard to test, tight coupling | Monolithic applications, simple CRUD | Not suitable |
| **Clean Architecture** | Similar to hexagonal, strong dependency rules | Complex, overkill for small systems | Large enterprise systems | Good alternative, more complex |
| **MVC** | Simple, framework support | Tight coupling, hard to test business logic | Web applications, simple domains | Not suitable for extraction pipeline |

## Consequences

### Positive
- Can test business logic without real database/queue
- Can swap SQLite → PostgreSQL without changing core code
- Can swap LocalFileSystem → GCS without changing core code
- Can run full pipeline in tests with mocks

### Negative
- More interfaces to maintain
- New team members need to learn the pattern
- Slightly more code upfront

## Defense Notes

**Q: Why not just use standard MVC?**
A: MVC couples business logic to framework/database. Our extraction pipeline needs to work with multiple storage backends (local files for dev, GCS for prod) and multiple databases (SQLite for MVP, BigQuery for analytics). Hexagonal lets us swap these without touching business logic.

**Q: Isn't this overkill for a take-home assignment?**
A: A Principal Engineer designs for production even in MVPs. This architecture proves I can build systems that scale and evolve.

**Q: How do you handle the extra complexity?**
A: The ports are simple interfaces (~5 methods each). The adapters for local dev are trivial implementations (~50 lines each). The complexity pays off immediately in testability.

## Implementation
- `ports/` - Interface definitions (storage, queue, database, llm)
- `adapters/` - Concrete implementations
- `services/` - Business logic using ports, unaware of implementations
```

### 2. ADR 002: Storage Strategy
File: `docs/adr/002_storage_strategy.md`

```markdown
# ADR 002: Storage Strategy - MVP vs Production

## Status
Accepted

## Context
We need different storage solutions for MVP (local development) and production. The system must handle document uploads, processing state, and extraction results.

## Decision
Use **SQLite** for MVP (local dev), design for **PostgreSQL + BigQuery** in production.

## Comparison

| Storage | Pros | Cons | Best For | Verdict |
|---------|------|------|----------|---------|
| **SQLite** | Zero setup, portable, single file, fast for small data | Not scalable, no concurrency, no replication | MVP, local dev, testing | **MVP CHOSEN** |
| **PostgreSQL** | ACID, scalable, JSON support, replication | Requires setup, connection management | Production OLTP | **Production choice** |
| **BigQuery** | Analytics optimized, unlimited scale, SQL interface | Append-only, high latency, expensive queries | Analytics, reporting | **Production analytics** |
| **DynamoDB** | Fully managed, scalable, fast | AWS lock-in, query limitations, cost | AWS ecosystems | Not chosen (GCP-focused) |
| **MongoDB** | Flexible schema, easy JSON | Not ACID, complex ops, data integrity concerns | Unstructured data | Not suitable (structured extraction) |

## Architecture

### MVP (SQLite)
- Single `extraction.db` file
- Three tables: submissions, documents, extraction_results
- JSON columns for flexible schema
- Indexed on file_hash for idempotency

### Production (PostgreSQL + BigQuery)
**PostgreSQL (Operational Database):**
- Submissions, documents, processing state
- Real-time queries for API
- Connection pooling

**GCS (Object Storage):**
- Document uploads
- Extraction output (JSON files)
- Signed URLs for temporary access

**BigQuery (Analytics Warehouse):**
- Structured extraction results
- Complex queries, aggregations
- Integration with BI tools

**Data Flow:**
```
Upload → GCS → Processing → PostgreSQL (state) + GCS (JSON) → Dataform ETL → BigQuery
```

## Consequences

### Positive
- MVP works immediately, no infrastructure setup
- Production architecture is clear
- Easy migration path: SQLite → PostgreSQL
- Analytics separate from operational DB

### Negative
- Two different schemas to maintain (SQLite vs BigQuery)
- ETL pipeline needed (Dataform)
- More complex than single database

## Defense Notes

**Q: Why not just use PostgreSQL for MVP too?**
A: SQLite requires zero setup. A reviewer can clone and run `just dev` without Docker, PostgreSQL, or cloud credentials. The repository pattern makes swapping trivial.

**Q: Why separate BigQuery from PostgreSQL?**
A: Separation of concerns. PostgreSQL handles real-time API queries (fast, ACID). BigQuery handles analytics (complex joins, aggregations, time-series). BigQuery's append-only design is perfect for audit trails.

**Q: How do you migrate from SQLite to PostgreSQL?**
A: The repository pattern abstracts the database. We just swap SQLiteAdapter for PostgreSQLAdapter. Schema migration handled by SQLAlchemy. Data migration is a one-time script.
```

### 3. ADR 003: LLM Choice
File: `docs/adr/003_llm_choice.md`

```markdown
# ADR 003: LLM Provider Selection

## Status
Accepted

## Context
We need an LLM for structured document extraction. Requirements: JSON output, document understanding (PDF), cost-effective, easy credentials for reviewers.

## Decision
Use **Gemini via Google AI Studio API Key** with PydanticAI framework.

## Comparison

| Provider | Pros | Cons | Best For | Verdict |
|----------|------|------|----------|---------|
| **Gemini (AI Studio)** | API key (no service account), free tier, DocumentUrl support, strong document understanding | Rate limits, newer model | Prototyping, small scale | **MVP CHOSEN** |
| **Gemini (VertexAI)** | Enterprise features, better SLA, higher quotas | Requires GCP service account, complex setup | Production at scale | Production alternative |
| **OpenAI GPT-4o** | Excellent JSON mode, widely used | More expensive, requires separate document parsing | General extraction | Good alternative |
| **Anthropic Claude** | Excellent at long documents, reasoning | DocumentUrl requires force_download for most formats | Complex documents | Good alternative |
| **Local LLM (Llama, etc)** | No API costs, data privacy | Infrastructure overhead, weaker extraction | Privacy-critical | Not suitable for assignment |

## Why PydanticAI?

| Framework | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **PydanticAI** | Native Pydantic integration, DocumentUrl support, type safety, structured output guaranteed | Newer, smaller community | **CHOSEN** |
| **LangChain** | Large ecosystem, many integrations | Bloated, abstraction leaks, version churn | Not chosen |
| **Instructor** | Good Pydantic integration, multiple providers | Requires separate document parsing | Good alternative |
| **Raw API** | Full control | Boilerplate, error handling, retry logic | Not suitable |

## Consequences

### Positive
- DocumentUrl handles PDF parsing automatically
- API key is simple (reviewer can provide their own)
- Pydantic ensures valid JSON output
- Native integration with Pydantic models

### Negative
- Gemini has rate limits (15 req/min on free tier)
- Must handle rate limiting with retries
- Vendor lock-in to Google (but adapters abstract this)

## Defense Notes

**Q: Why not use OpenAI?**
A: OpenAI is excellent but requires more setup for document parsing (no native DocumentUrl support). Gemini's DocumentUrl passes the PDF directly to the model. For this assignment, simplicity wins.

**Q: What if Gemini fails or is unavailable?**
A: The LLMPort abstraction allows swapping to OpenAI or Anthropic by implementing a new adapter. The core extraction logic is provider-agnostic.

**Q: How do you handle rate limits?**
A: Stamina library provides exponential backoff with jitter. We retry 3 times with increasing delays (1s, 2s, 4s). For production, we'd add request queueing.

**Q: Why PydanticAI over LangChain?**
A: LangChain is overkill for this use case. PydanticAI is purpose-built for structured output with Pydantic. It's 10x smaller, faster, and has native DocumentUrl support. LangChain's abstraction leaks cause debugging nightmares.
```

### 4. ADR 004: State Machine (Pydantic Graph)
File: `docs/adr/004_state_machine.md`

```markdown
# ADR 004: Processing Pipeline - State Machine

## Status
Accepted

## Context
Document extraction needs a multi-step pipeline: validation → extraction → validation. We need error handling, retries, and clear state transitions.

## Decision
Use **Pydantic Graph** for state machine orchestration.

## Comparison

| Orchestration | Pros | Cons | Best For | Verdict |
|---------------|------|------|----------|---------|
| **Pydantic Graph** | Type-safe, Pydantic-native, simple, async | Newer, less mature ecosystem | Python data pipelines | **CHOSEN** |
| **Airflow** | Mature, UI, scheduling | Heavy, complex, overkill for simple pipelines | Complex DAGs, scheduling | Too complex |
| **Temporal** | Durable execution, retries, observability | Complex, requires server | Long-running workflows | Overkill |
| **Celery** | Distributed tasks, mature | Requires broker (Redis), complex setup | Distributed task queues | Too complex |
| **Simple Functions** | Minimal code, easy to understand | No error handling, no retries, hard to debug | Tiny scripts | Not suitable |
| **State Machine (transitions)** | Pythonic, diagram generation | Sync only, limited async support | State machines | Good alternative |

## Pipeline Design

```
[PreprocessNode] → [ExtractNode] → [ValidateNode]
      ↓                    ↓               ↓
   Validation         Extraction      Final Output
   Failed?            Failed?         (completed/partial/manual_review)
      ↓                    ↓
   End(failed)       End(failed)
```

### Nodes
1. **PreprocessNode**: Validate file existence, size, type, password protection
2. **ExtractNode**: PydanticAI extraction with Gemini
3. **ValidateNode**: Logical validation (positive income, valid dates, confidence threshold)

## Consequences

### Positive
- Clear, type-safe state transitions
- Easy to test each node independently
- Async native (supports I/O-bound operations)
- Error handling at each step

### Negative
- Pydantic Graph is newer (risk of API changes)
- Not as battle-tested as Airflow/Temporal

## Defense Notes

**Q: Why not Airflow?**
A: Airflow is a sledgehammer for this nut. We have a 3-node linear pipeline, not a complex DAG. Airflow requires a database, scheduler, webserver - overkill for this assignment.

**Q: What if Pydantic Graph has bugs?**
A: It's built by the Pydantic team (same people behind FastAPI). The code is simple (~500 lines). We can vendor it if needed. The abstraction is thin enough that we could swap to plain async functions.

**Q: How do you handle failures?**
A: Each node returns either the next node or an End state. Errors are caught and routed to End(failed). For production, we'd add a Dead Letter Queue.

**Q: Can you add more nodes later?**
A: Yes. Just add a new node class and update the graph definition. The pattern supports complex branching if needed.
```

### 5. ADR 005: Event-Driven Design
File: `docs/adr/005_event_driven_design.md`

```markdown
# ADR 005: Event-Driven Architecture

## Status
Accepted for Production, Documented for MVP

## Context
The extraction pipeline should be asynchronous to handle long-running operations without blocking API requests.

## Decision
**MVP**: Synchronous processing with documented event-driven architecture.
**Production**: Async with Pub/Sub queue.

## Comparison

| Approach | Pros | Cons | Best For | Verdict |
|----------|------|------|----------|---------|
| **Synchronous** | Simple, no infrastructure, easy to debug | Blocks requests, no retry on failure, couples upload to processing | MVP, simple demos | **MVP CHOSEN** |
| **Async Queue (Pub/Sub)** | Decoupled, retry logic, scalable, fault-tolerant | Infrastructure overhead, complex debugging | Production, scale | **Production** |
| **Async (Celery)** | Distributed, mature | Requires broker (Redis), complex ops | Distributed tasks | Alternative |
| **Hybrid (202 Accepted + Polling)** | Good UX, decoupled | Complex client logic | User-facing APIs | Alternative |

## MVP Implementation

API returns 202 Accepted immediately:
```python
@router.post("/upload")
async def upload(files: list[UploadFile]):
    # Save files
    # Create submission record
    # TODO: Publish event to queue
    return {"submission_id": "...", "status": "accepted"}
```

Queue is documented but not implemented:
```python
# TODO: In production, publish to Pub/Sub
# await queue.publish("document-uploaded", {...})
```

## Production Architecture

```
Upload API → Pub/Sub (document-uploaded) → Cloud Run Workers
                                            ↓
                    Pub/Sub (extraction-completed) → BigQuery ETL
```

## Consequences

### Positive
- MVP works without queue infrastructure
- Production path is clear
- Can test core logic without queue

### Negative
- MVP doesn't truly test async behavior
- Production will need different testing approach

## Defense Notes

**Q: Why not implement the queue in MVP?**
A: Time constraint. The core logic (extraction, validation) is identical. The queue is plumbing. By designing the ports (QueuePort), we've prepared for the queue swap.

**Q: How do you test the async behavior?**
A: The processing graph is pure async. It can be called directly in tests. The queue just triggers it. We test the graph extensively.

**Q: What happens if extraction takes >30 seconds?**
A: In MVP, API may timeout. Production with queue handles this fine. We document this limitation.
```

### 6. ADR 006: Horizontal Scaling
File: `docs/adr/006_horizontal_scaling.md`

```markdown
# ADR 006: Horizontal Scaling Strategy

## Status
Accepted

## Context
System must handle 10x and 100x volume increases from initial load.

## Decision
Use **Cloud Run auto-scaling** with stateless workers.

## Scaling Strategy

### Current (MVP)
- Single container
- SQLite database
- Local file storage
- Handles: ~10 docs/minute

### 10x Volume
**Changes:**
- Cloud Run with 2-20 instances
- PostgreSQL (managed)
- GCS for storage
- Keep sync API

**Capacity:** ~100 docs/minute

**Infrastructure:**
```hcl
min_instances = 2
max_instances = 20
concurrency = 10  # requests per instance
```

### 100x Volume
**Changes:**
- Pub/Sub queue
- Separate worker pool
- BigQuery for results
- Shard by document hash

**Capacity:** ~1000+ docs/minute

**Architecture:**
```
Load Balancer → Cloud Run (API) → Pub/Sub → Cloud Run Workers (pool)
                                              ↓
                                      GCS + BigQuery
```

## Scaling Bottlenecks

| Component | Current | 10x Strategy | 100x Strategy |
|-----------|---------|--------------|---------------|
| **Compute** | Single container | Cloud Run auto-scale | Separate worker pool |
| **Storage** | SQLite | PostgreSQL (Cloud SQL) | PostgreSQL + Read replicas |
| **Files** | Local disk | GCS | GCS with lifecycle |
| **Queue** | None (sync) | Still sync | Pub/Sub |
| **Analytics** | None | BigQuery | BigQuery + Dataform |

## Consequences

### Positive
- Stateless design enables easy scaling
- Cloud Run handles 90% of scaling needs
- Queue adds only when necessary

### Negative
- 100x requires significant infrastructure
- Cost increases linearly with volume

## Defense Notes

**Q: How do you handle state (SQLite) when scaling?**
A: SQLite doesn't scale. At 10x we swap to PostgreSQL. The repository pattern makes this a one-line change. Cloud SQL provides managed PostgreSQL.

**Q: What about concurrent file uploads?**
A: GCS handles this natively. Each upload gets a unique path (submission_id/filename).

**Q: Rate limiting on Gemini API?**
A: At 100x volume, we'd need to:
1. Request quota increase from Google
2. Implement request batching
3. Cache similar documents
4. Consider model cascading (cheaper model for simple docs)
```

### 7. ADR 007: Construction Submittal Pivot
File: `docs/adr/007_construction_submittal_pivot.md`

```markdown
# ADR 007: Domain Extension - Construction Submittals

## Status
Accepted (Documentation Only)

## Context
The system should be extensible to other document types, specifically construction submittals.

## Analysis

### Loan Documents vs Construction Submittals

| Aspect | Loan Documents | Construction Submittals | Similarity |
|--------|----------------|------------------------|------------|
| **Core Task** | Extract PII, income, accounts | Extract materials, specs, approvals | Same: Structured extraction |
| **Input** | PDFs, bank statements | PDFs, CAD drawings, specs | Same: Document processing |
| **Output Schema** | BorrowerProfile | SubmittalPackage | Different: Domain-specific |
| **Validation** | Income > 0, valid dates | Spec compliance, approval status | Same: Rule-based validation |
| **Provenance** | Page + text snippet | Drawing reference + spec section | Same: Source tracking |
| **Confidence** | Financial accuracy | Spec compliance accuracy | Same: Quality metric |

## System Adaptability

Our architecture supports this pivot with minimal changes:

### What Stays the Same
- Hexagonal Architecture (ports/adapters)
- Storage layer (GCS, SQLite/PostgreSQL)
- Queue system (Pub/Sub)
- State machine (Pydantic Graph)
- LLM integration (PydanticAI + Gemini)
- API structure (upload, query, status)

### What Changes

#### 1. Domain Models
```python
# New file: src/doc_extract/domain/submittal.py

class SubmittalPackage(BaseModel):
    """Construction submittal package."""
    submittal_id: str
    project_id: str
    contractor: ContractorInfo
    materials: list[MaterialSpec]
    specifications: list[SpecReference]
    approval_status: ApprovalStatus
    review_date: date | None
    engineer_comments: str | None
    provenance: Provenance  # Reuse existing
```

#### 2. System Prompt
```markdown
# New file: prompts/submittal_extraction.md

Extract:
- Project information (name, ID, location)
- Contractor details (name, license)
- Material specifications (product, manufacturer, model)
- Spec references (section, paragraph)
- Approval status (approved, rejected, pending)
- Engineer comments and review date
```

#### 3. Validation Rules
```python
# New validation rules
- Material must have manufacturer and model
- Spec reference must match project spec book
- Approval date must be after submission date
- Rejected submittals must have comments
```

#### 4. API Endpoints
```python
@router.post("/submittals/upload")
async def upload_submittal(files: list[UploadFile]):
    # Same logic, different document type
    pass

@router.get("/submittals/{submittal_id}")
async def get_submittal(submittal_id: str):
    # Returns SubmittalPackage instead of BorrowerProfile
    pass
```

### Migration Path

1. **Add new domain models** (submittal.py)
2. **Add new system prompt** (submittal_extraction.md)
3. **Add new validation rules** (submittal_validation.py)
4. **Add new API routes** (submittal_routes.py)
5. **Reuse all infrastructure** (storage, queue, database)

### Effort Estimate
- Domain models: 4 hours
- System prompt: 1 hour
- Validation rules: 2 hours
- API routes: 2 hours
- Testing: 4 hours
- **Total: ~13 hours** (vs 40+ hours for new system)

## Consequences

### Positive
- Proves architecture is domain-agnostic
- 70% code reuse between use cases
- Same infrastructure works for both

### Negative
- Domain models can't be fully shared (different schemas)
- Separate extraction prompts needed
- Testing requires separate ground truth datasets

## Defense Notes

**Q: How do you handle completely different document types?**
A: The core extraction loop is identical: validate → extract → validate. Only the schema and prompts change. The LLM handles the document understanding.

**Q: What if we need both in the same system?**
A: Add a "document_type" discriminator. Route to appropriate pipeline. Share infrastructure, separate business logic.

**Q: Could this work for medical records? Legal contracts?**
A: Yes. Same pattern applies. The architecture is truly domain-agnostic. Only the Pydantic schemas and prompts are domain-specific.
```

## Deliverables
- [ ] docs/adr/001_hexagonal_architecture.md
- [ ] docs/adr/002_storage_strategy.md
- [ ] docs/adr/003_llm_choice.md
- [ ] docs/adr/004_state_machine.md
- [ ] docs/adr/005_event_driven_design.md
- [ ] docs/adr/006_horizontal_scaling.md
- [ ] docs/adr/007_construction_submittal_pivot.md
- [ ] All ADRs have comparison tables with 3+ alternatives
- [ ] All ADRs have defense notes for interview questions

## Success Criteria
- All 7 ADRs are complete
- Each ADR has Pros/Cons/Best For/Verdict table
- Defense notes prepare for 5+ hostile questions per ADR
- ADRs reference each other where appropriate
- Architecture decisions are defensible

## Next Prompt
After this completes, move to `15_documentation.md` for README and SYSTEM_DESIGN.md.
