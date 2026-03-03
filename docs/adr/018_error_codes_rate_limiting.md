# ADR 018: Structured Error Codes & Rate Limiting

## Status
**Accepted** - 2026-03-02

## Context
We need comprehensive, structured error handling with enum-based error codes and production-grade rate limiting. This is a "Head of Engineering" level feature demonstrating API design and operational excellence.

## Purpose
This decision impacts:
- **Developer Experience**: Clear error messages for API consumers
- **Debugging**: Programmatically identify error types
- **Security**: Prevent abuse via rate limiting
- **Compliance**: Audit trail for errors

## Alternatives Considered

| Alternative | Pros | Cons | Best For |
|-------------|------|------|----------|
| **Enum + SlowAPI (Chosen)** | Structured + built-in | Two components | Python APIs |
| Custom middleware | Full control | Reinventing | Unique needs |
| API Gateway | Managed solution | External dependency | Enterprise |
| No rate limiting | Simple | Vulnerable to abuse | Internal only |

## Detailed Pros and Cons

### Enum Error Codes + SlowAPI (Chosen)

**Pros:**
- **Structured** - Enum-based error codes
- **Built-in** - SlowAPI handles rate limiting
- **Standard** - Follows industry conventions
- **Programmatic** - Easy to handle in code
- **Documented** - Clear error codes

**Cons:**
- **Two libraries** - Need to integrate
- **Custom error codes** - Must define ourselves
- **SlowAPI-specific** - Tied to library

### Custom Middleware

**Pros:**
- **Full control** - Do anything
- **No dependencies** - Minimal

**Cons:**
- **Complex** - Must implement everything
- **Bug-prone** - Easy to make mistakes
- **Maintenance** - Own it forever

### API Gateway

**Pros:**
- **Managed** - No code to maintain
- **Additional features** - Auth, caching, etc.

**Cons:**
- **External dependency** - Another service
- **Cost** - Gateway costs money
- **Complexity** - More infrastructure

## Conclusion

We chose **Enum Error Codes + SlowAPI** because:

1. **Structured** - Clear error categorization
2. **Industry standard** - Follows best practices
3. **Easy to use** - Simple integration
4. **Head of Engineering** - Demonstrates API design skill
5. **Fast to implement** - Built on existing libs

## Error Code Structure

```python
from enum import Enum

class ErrorCode(str, Enum):
    # Validation errors (1xxx)
    VALIDATION_ERROR = "E1001"
    INVALID_DOCUMENT_TYPE = "E1002"
    MISSING_REQUIRED_FIELD = "E1003"
    
    # Processing errors (2xxx)
    PROCESSING_ERROR = "E2001"
    EXTRACTION_FAILED = "E2002"
    VALIDATION_FAILED = "E2003"
    
    # LLM errors (3xxx)
    LLM_ERROR = "E3001"
    LLM_TIMEOUT = "E3002"
    LLM_RATE_LIMIT = "E3003"
    
    # Storage errors (4xxx)
    STORAGE_ERROR = "E4001"
    FILE_NOT_FOUND = "E4002"
    
    # Rate limiting (5xxx)
    RATE_LIMIT_EXCEEDED = "E5001"
```

### HTTP Status Mapping

| Category | Status Code | Example |
|----------|-------------|---------|
| Validation | 400 | Invalid input |
| Auth | 401 | Unauthorized |
| Not Found | 404 | Resource missing |
| Rate Limit | 429 | Too many requests |
| Server Error | 500 | Internal failure |

## Rate Limiting

### Configuration

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/documents/upload")
@limiter.limit("10/minute")  # 10 requests per minute
async def upload_document(file: UploadFile):
    # Upload logic
```

### Limits by Endpoint

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| /upload | 10/min | Heavy operation |
| /query | 60/min | Light operation |
| /health | 100/min | Read-only |

## Standardized Error Response

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

## Consequences

### Positive
- Clear error codes for debugging
- Automatic rate limiting
- Standardized error format
- Easy to add new error types
- Programmatic error handling

### Negative
- Additional complexity
- Must document error codes
- Need to handle in clients

## Implementation

See:
- `src/doc_extract/core/error_codes.py` - Error code enum (planned)
- `src/doc_extract/core/exceptions.py` - Exception classes
- Uses slowapi in pyproject.toml

## Review Schedule
Review after 3 months to assess if error handling is working well.