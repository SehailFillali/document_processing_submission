# Document Extraction System

A resilient, event-driven document extraction platform for unstructured data using modern Python stack with PydanticAI and OpenAI/Gemini.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- [just](https://github.com/casey/just) (command runner — used for all project tasks)
- Docker & Docker Compose (for containerized services)

## Quick Start

### 1. Clone and Setup

```bash
# Install dependencies with uv
just setup
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API key
# Required: OPENAI_API_KEY or GEMINI_API_KEY
```

### 3. Start Development Server

```bash
# Option A: Local development
just dev

# Option B: Full stack with Docker (includes MinIO, optional Postgres)
docker-compose up
```

The API will be available at `http://localhost:8000`

### 4. Verify It's Working

```bash
curl http://localhost:8000/health
```

## End-to-End Usage Example

### Step 1: Upload a Document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/loan_document.pdf" \
  -F "document_type=loan_application"
```

**Response:**
```json
{
  "submission_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "message": "Document uploaded successfully. Processing will begin shortly."
}
```

### Step 2: Poll for Status

```bash
# Replace with your submission_id
curl http://localhost:8000/api/v1/submissions/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Response:**
```json
{
  "submission_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "borrower_profile": {
    "borrower_id": "...",
    "name": "John Doe",
    "address": {
      "street": "123 Main Street",
      "city": "Springfield",
      "state": "IL",
      "zip_code": "62701",
      "country": "US"
    },
    "income_history": [
      {
        "amount": 75000.0,
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "source": "ABC Corporation",
        "provenance": {
          "source_document": "loan_document.pdf",
          "source_page": 2,
          "confidence_score": 0.95
        }
      }
    ],
    "accounts": [...],
    "extraction_confidence": 0.92
  }
}
```

### Step 3: List All Submissions

```bash
curl http://localhost:8000/api/v1/submissions
```

## API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /api/v1/documents/upload | Upload document for extraction |
| GET | /api/v1/submissions/{id} | Get submission by ID |
| GET | /api/v1/submissions | List all submissions |

### Blob Storage Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/documents/process_uploaded_blob | Process document from S3/GCS/MinIO |
| GET | /api/v1/blob/health | Check blob storage connectivity |

### Observability Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/costs | Get LLM cost summary |
| GET | /metrics | Prometheus-compatible metrics |

### Error Handling Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/errors/codes | List all error codes |

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (primary) |
| `GEMINI_API_KEY` | Google Gemini API key (alternative) |

### Storage Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `local` | Storage type: local, minio, s3, gcs |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO server endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET_NAME` | `documents` | MinIO bucket name |
| `AWS_S3_BUCKET` | - | AWS S3 bucket name |
| `AWS_REGION` | `us-east-1` | AWS region |

### Application Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `local` | Environment: local, dev, prod |
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |
| `SERVER_PORT` | `8000` | Server port |
| `DATABASE_URL` | `sqlite:///./data/extraction.db` | Database connection string |

### Resilience Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable circuit breaker |
| `CIRCUIT_BREAKER_THRESHOLD` | `5` | Failures before opening |
| `CIRCUIT_BREAKER_TIMEOUT` | `30` | Seconds before half-open |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_UPLOAD` | `10/min` | Upload rate limit |
| `RATE_LIMIT_QUERY` | `60/min` | Query rate limit |

### Observability Configuration

| Variable | Description |
|----------|-------------|
| `LOGFIRE_TOKEN` | Logfire token for observability |
| `LOGFIRE_ENABLED` | Enable Logfire (default: false) |

## Just Commands

| Command | Description |
|---------|-------------|
| `just setup` | Install dependencies with uv |
| `just dev` | Run development server |
| `just test` | Run tests with coverage |
| `just lint` | Run linting (ruff, mypy) |
| `just format` | Format code |
| `just build-image` | Build Docker image |
| `just dev-docker` | Run with Docker Compose |
| `just evaluate` | Run evaluation script |
| `just clean` | Clean cache files |
| `just ci` | Run full CI pipeline |

## Docker Compose Services

The stack includes:

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | Main FastAPI application |
| MinIO | 9000/9001 | S3-compatible storage + console |
| PostgreSQL | 5432 | Optional: production database |

### Starting with MinIO

```bash
# Start with MinIO
docker-compose --profile minio up

# Access MinIO console at http://localhost:9001
# Credentials: minioadmin / minioadmin
```

### Starting with PostgreSQL

```bash
# Start with PostgreSQL
docker-compose --profile postgres up

# Full stack with all services
docker-compose --profile minio --profile postgres up
```

## Test Coverage

Current coverage: **80%+** across all modules.

### Running Tests

```bash
# Run all tests with coverage report
just test

# Run specific test file
pytest tests/test_api.py -v

# Run with coverage output
pytest tests/ --cov=src/doc_extract --cov-report=term-missing --cov-report=html
```

### Test Structure

```
tests/
├── test_domain.py          # Domain model validation
├── test_adapters.py        # Adapter functionality
├── test_api.py             # API endpoints
├── test_services.py        # Service layer
├── test_ports.py           # Port interfaces
├── test_validation.py      # Validation logic
├── test_edge_cases.py      # Edge case handling
├── test_sqlite_adapter.py  # Database tests
├── test_minio_adapter.py   # Storage tests
├── integration/            # Integration tests
└── evaluation/             # Golden set evaluation
    ├── run_eval.py         # Evaluation script
    └── golden_set.json     # Test data
```

## Resilience Features

### Circuit Breaker

Automatically prevents cascade failures when external services (LLM, storage) are unavailable.

- Opens after 5 consecutive failures
- Half-open after 30 seconds
- Closes after successful call

### Rate Limiting

Per-endpoint rate limiting to prevent abuse:

| Endpoint | Limit |
|----------|-------|
| `/api/v1/documents/upload` | 10/min |
| `/api/v1/documents/process_uploaded_blob` | 10/min |
| `/api/v1/submissions/{id}` | 60/min |
| `/api/v1/submissions` | 60/min |

### Structured Error Codes

All errors include machine-readable codes:

```json
{
  "error": {
    "code": "E2001",
    "message": "Document processing failed",
    "details": {
      "stage": "extraction",
      "reason": "LLM returned invalid JSON"
    },
    "timestamp": "2026-03-02T15:30:00Z"
  }
}
```

Error code ranges:
- `1xxx`: Validation errors
- `2xxx`: Processing errors
- `3xxx`: LLM errors
- `4xxx`: Storage errors
- `5xxx`: Rate limiting

## Extracted Data Schema

For loan documents, the system extracts:

### BorrowerProfile

| Field | Type | Description |
|-------|------|-------------|
| `borrower_id` | string | Unique identifier |
| `name` | string | Full name |
| `address` | Address | Physical address |
| `phone` | string | Phone number |
| `email` | string | Email address |
| `ssn_last_four` | string | Last 4 SSN digits |
| `income_history` | list[IncomeEntry] | Employment/income records |
| `accounts` | list[AccountInfo] | Loan/account details |
| `extraction_confidence` | float | Overall confidence (0-1) |
| `requires_manual_review` | bool | Needs human review |

### Sub-fields

**Address:** street, city, state (2-letter), zip_code, country

**IncomeEntry:** amount, period_start, period_end, source, provenance

**Provenance:** source_document, source_page, verbatim_text, confidence_score

## Documentation

- [System Design](SYSTEM_DESIGN.md) - Detailed architecture
- [Architecture Decision Records](docs/adr/) - Technical decisions
- API Documentation - Available at `/docs` when running

## Development

```bash
# Setup
just setup

# Run in development
just dev

# Run tests
just test

# Lint and format
just lint
just format

# Build and run with Docker
just build-image
just dev-docker

# Run evaluation
just evaluate
```

## Architecture Highlights

- **Hexagonal Architecture** — Every external dependency (LLM, storage, database, queue) is behind an abstract port. Adapters can be swapped without touching business logic. This enables parallel team development and frictionless infrastructure changes when scaling. See [ADR 001](docs/adr/001_hexagonal_architecture.md).

- **PydanticAI + Structured Output** — LLM responses are constrained to exact Pydantic schemas via `response_format: json_schema`. This prevents hallucinated field names and types, and ensures every extraction result is type-safe and validated. See [ADR 003](docs/adr/003_llm_provider.md).

- **Native PDF Ingestion** — Documents are sent directly to multimodal LLMs that process PDFs natively, preserving table structure, forms, and spatial layout. This eliminates the need for a local PDF parsing pipeline. See [ADR 024](docs/adr/024_native_llm_pdf_ingestion.md).

- **Self-Correction Loop** — Extractions are verified by a Critic Agent (a second LLM call). If the QA score falls below 80%, feedback is injected into the extraction prompt and the extraction is retried (up to 2 times). The best result across all attempts is returned. See [ADR 020](docs/adr/020_multi_critic_panel.md).

- **Production Resilience** — Circuit breaker (prevents cascade failures), token-bucket rate limiting (per-client, multi-window), 30 structured error codes, and Prometheus metrics (11 custom metrics). These are not "nice-to-haves" — they're the minimum for a deployable system. See [ADR 016](docs/adr/016_circuit_breaker_resilience.md), [ADR 018](docs/adr/018_error_codes_rate_limiting.md).

- **Multi-Storage / Multi-LLM** — Local, MinIO, S3, GCS storage via adapter pattern. OpenAI and Gemini LLM providers via `LLMPort`. Configuration-driven backend selection — changing `STORAGE_BACKEND=minio` or swapping LLM providers requires zero code changes. See [ADR 010](docs/adr/010_llm_provider_selection.md), [ADR 015](docs/adr/015_minio_blob_storage.md).

See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for full architecture details and [docs/adr/](docs/adr/) for all 24 Architecture Decision Records.