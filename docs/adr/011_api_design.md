# ADR 011: REST API Design with FastAPI

## Status
**Accepted** - 2026-03-02

## Context
We need to design the API endpoints for document ingestion, processing, and retrieval. The assignment requires a query interface for extracted data. We chose FastAPI, but need to document the design decisions.

## Purpose
This decision impacts:
- **Developer Experience**: How easy the API is to use and understand
- **Integration**: How well other systems can integrate
- **Performance**: API latency and throughput
- **Documentation**: Auto-generated API docs
- **Scalability**: How the API handles load

## Alternatives Considered

| Alternative | Pros | Cons | Best For |
|-------------|------|------|----------|
| **FastAPI (Chosen)** | Async native, auto-docs | Less mature than Flask | Modern Python apps |
| Flask | Simple, flexible | No async, manual docs | Simple APIs |
| Django REST | Full framework | Heavy, complex | Django projects |
| aiohttp | Lightweight async | Minimal features | Microservices |
| Starlette | Fast, flexible | Less abstraction | Custom frameworks |

## Detailed Pros and Cons

### FastAPI (Chosen)

**Pros:**
- **Native async** - Built on Starlette, fully async
- **Auto OpenAPI** - Automatic API documentation at /docs
- **Pydantic integration** - Request/response validation
- **Performance** - One of the fastest Python frameworks
- **Type hints** - Great IDE support
- **Dependency injection** - Clean testing via Depends()
- **WebSocket support** - For real-time features
- **Background tasks** - For async processing

**Cons:**
- **Learning curve** - Must understand async/await
- **Less mature** - Newer than Flask/Django
- **ASGI required** - Need Uvicorn/Hypercorn
- **Validation overhead** - Pydantic can be slow for large payloads

### Flask

**Pros:**
- **Simple** - Easy to understand
- **Flexible** - Minimal constraints
- **Mature** - Battle-tested
- **Large ecosystem** - Many extensions

**Cons:**
- **No native async** - Requires additional libraries
- **Manual docs** - Must use Flask-RESTful or similar
- **Validation** - Need external libraries (marshmallow)

### Django REST Framework

**Pros:**
- **Full-featured** - Everything included
- **ORM integration** - Built-in database integration
- **Authentication** - Built-in auth system

**Cons:**
- **Heavy** - Overkill for small services
- **Complex** - Steep learning curve
- **Synchronous** - Not async-native

## Conclusion

We chose **FastAPI** because:

1. **Async-first** - Document processing is I/O-bound, async is ideal
2. **Pydantic native** - Seamless integration with our domain models
3. **Auto documentation** - Reviewers can explore API without reading code
4. **Performance** - Critical for 10x/100x scaling requirements
5. **Modern stack** - Matches our PydanticAI + uv choices

## API Design Principles

### 1. RESTful Conventions
- Resource-based URLs: `/api/v1/documents`, `/api/v1/submissions`
- HTTP verbs: GET for retrieval, POST for creation
- Status codes: 200 for success, 404 for not found, 500 for errors

### 2. Versioning
- `/api/v1/` prefix for future compatibility
- Allows breaking changes without affecting existing clients

### 3. Idempotency
- Upload endpoint generates unique submission_id
- Safe to retry requests

### 4. Response Consistency
- All responses use Pydantic models
- Consistent error response format

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /api/v1/documents/upload | Upload document for processing |
| GET | /api/v1/submissions/{id} | Get submission status |
| GET | /api/v1/submissions | List submissions |
| POST | /api/v1/documents/process_uploaded_blob | Process from blob storage |
| GET | /api/v1/blob/health | Blob storage health check |

## Consequences

### Positive
- Auto-generated interactive documentation
- Type-safe request/response validation
- Easy to add async background processing
- Great for scaling via async workers
- Clean dependency injection for testing

### Negative
- Team needs to understand async
- Learning curve for Pydantic/FastAPI integration
- Must use ASGI server (Uvicorn)

## Implementation

See:
- `src/doc_extract/api/main.py` - Main FastAPI application
- `src/doc_extract/api/blob_endpoints.py` - Blob storage endpoints

## Review Schedule
Review in 6 months to assess if API design meets integration needs.
