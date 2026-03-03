# Prompt 07: API Endpoints - FastAPI Routes

## Status
[PARTIALLY_IMPLEMENTED] - routes consolidated in main.py, not split into routes/ subdirectory

## Context
Creating the REST API interface for document ingestion and querying using FastAPI.

## Objective
Implement FastAPI routes for upload, status check, and query endpoints with proper validation and error handling.

## Requirements

### 1. Create FastAPI Application Main
File: `src/doc_extract/api/main.py`

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from doc_extract.core.config import settings
from doc_extract.core.logging import setup_logging, logger
from doc_extract.core.exceptions import DocExtractError
from doc_extract.api.routes import ingestion, query, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    setup_logging(settings.log_level)
    logger.info(f"Starting Document Extraction API in {settings.environment} mode")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Document Extraction API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Document Extraction API",
        description="AI-powered document extraction for loan documents",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Global exception handler
    @app.exception_handler(DocExtractError)
    async def doc_extract_exception_handler(request: Request, exc: DocExtractError):
        """Handle custom application exceptions."""
        logger.error(
            f"Exception: {exc.error_code} - {exc.message}",
            extra={"details": exc.details}
        )
        
        return JSONResponse(
            status_code=400 if exc.error_code == "VALIDATION_ERROR" else 500,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "trace_id": getattr(request.state, "trace_id", None)
            }
        )
    
    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(ingestion.router, prefix="/api/v1", tags=["Ingestion"])
    app.include_router(query.router, prefix="/api/v1", tags=["Query"])
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "doc_extract.api.main:app",
        host=settings.server_ip,
        port=settings.server_port,
        reload=settings.environment == "local"
    )
```

### 2. Create Health Check Route
File: `src/doc_extract/api/routes/health.py`

```python
"""Health check endpoints."""
from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    from doc_extract.core.config import settings
    
    return HealthResponse(
        status="healthy",
        environment=settings.environment
    )


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness check for Kubernetes/Cloud Run."""
    # Check critical dependencies
    # TODO: Add database connection check
    # TODO: Add LLM service check
    
    return {"status": "ready"}
```

### 3. Create Ingestion Routes
File: `src/doc_extract/api/routes/ingestion.py`

```python
"""Document ingestion endpoints."""
import hashlib
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel, Field

from doc_extract.core.config import settings
from doc_extract.core.logging import logger
from doc_extract.core.exceptions import ValidationError, StorageError
from doc_extract.domain.submission import DocumentSubmission, SubmissionStatus, DocumentMetadata
from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.sqlite_db import SQLiteAdapter

router = APIRouter()

# Initialize adapters (will be dependency injected in production)
storage = LocalFileSystemAdapter("./uploads")
db = SQLiteAdapter(settings.database_url)


class UploadResponse(BaseModel):
    """Response for document upload."""
    submission_id: str
    status: str
    message: str
    document_count: int


class UploadRequest(BaseModel):
    """Upload request with metadata."""
    document_type: Optional[str] = Field(None, description="Type of document")
    borrower_id: Optional[str] = Field(None, description="Optional borrower identifier")


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    files: list[UploadFile] = File(..., description="Documents to upload (PDF, JSON)"),
    document_type: Optional[str] = Form(None),
    borrower_id: Optional[str] = Form(None)
):
    """Upload documents for extraction.
    
    Accepts multiple files and returns a submission ID for tracking.
    Files are hashed for idempotency - duplicate uploads return existing submission.
    
    Returns 202 Accepted immediately. Processing happens asynchronously.
    """
    # Validate file count
    if len(files) > 10:
        raise ValidationError("Maximum 10 files per upload", {"max_allowed": 10})
    
    # Generate submission ID
    submission_id = str(uuid.uuid4())
    
    documents = []
    
    for file in files:
        # Validate file size
        content = await file.read()
        file_size = len(content)
        
        if file_size > settings.max_file_size_mb * 1024 * 1024:
            raise ValidationError(
                f"File {file.filename} exceeds {settings.max_file_size_mb}MB limit",
                {"file": file.filename, "size_mb": file_size / (1024 * 1024)}
            )
        
        # Validate file extension
        ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        if f".{ext}" not in settings.allowed_extensions:
            raise ValidationError(
                f"File type .{ext} not allowed",
                {"allowed": settings.allowed_extensions}
            )
        
        # Calculate hash for idempotency
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Check if file already exists (idempotency check)
        existing = await check_existing_submission(file_hash)
        if existing:
            logger.info(f"Duplicate upload detected, returning existing submission {existing}")
            return UploadResponse(
                submission_id=existing,
                status="existing",
                message="Document already uploaded, returning existing submission",
                document_count=1
            )
        
        # Upload to storage
        storage_path = f"{submission_id}/{file.filename}"
        from io import BytesIO
        
        try:
            metadata = await storage.upload(
                BytesIO(content),
                storage_path,
                content_type=file.content_type or "application/octet-stream"
            )
        except Exception as e:
            raise StorageError(f"Failed to upload {file.filename}: {str(e)}")
        
        # Create document metadata
        doc_metadata = DocumentMetadata(
            document_id=str(uuid.uuid4()),
            file_hash=file_hash,
            file_name=file.filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            document_type=document_type or "unknown"
        )
        documents.append(doc_metadata)
        
        logger.info(f"Uploaded {file.filename} to {storage_path}")
    
    # Create submission record
    submission = DocumentSubmission(
        submission_id=submission_id,
        status=SubmissionStatus.PENDING,
        documents=documents,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # Persist to database
    await db.create("submissions", submission.model_dump())
    
    # TODO: Publish event to queue for async processing
    # await queue.publish("document-uploaded", {
    #     "submission_id": submission_id,
    #     "documents": [d.model_dump() for d in documents]
    # })
    
    logger.info(f"Created submission {submission_id} with {len(documents)} documents")
    
    return UploadResponse(
        submission_id=submission_id,
        status="accepted",
        message="Documents uploaded successfully, processing queued",
        document_count=len(documents)
    )


async def check_existing_submission(file_hash: str) -> Optional[str]:
    """Check if a file with this hash has already been submitted."""
    # Query database for existing submission with this hash
    result = await db.query(
        "submissions",
        filters=[{"field": "documents.file_hash", "operator": "eq", "value": file_hash}]
    )
    
    if result.items:
        return result.items[0].get("submission_id")
    
    return None


@router.get("/submissions/{submission_id}")
async def get_submission_status(submission_id: str):
    """Get status of a submission."""
    submission_data = await db.read("submissions", submission_id)
    
    if not submission_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found"
        )
    
    return submission_data
```

### 4. Create Query Routes
File: `src/doc_extract/api/routes/query.py`

```python
"""Query endpoints for extraction results."""
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from doc_extract.adapters.sqlite_db import SQLiteAdapter, QueryFilter
from doc_extract.core.config import settings

router = APIRouter()
db = SQLiteAdapter(settings.database_url)


class BorrowerQuery(BaseModel):
    """Query parameters for borrower search."""
    name: Optional[str] = Field(None, description="Borrower name (partial match)")
    ssn_last_four: Optional[str] = Field(None, pattern=r"^\d{4}$")
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class ExtractionResultResponse(BaseModel):
    """Response for extraction result query."""
    submission_id: str
    borrower_profile: Optional[dict]
    confidence_score: float
    source_documents: List[str]
    created_at: str


@router.get("/borrowers/search")
async def search_borrowers(
    name: Optional[str] = Query(None, description="Borrower name"),
    ssn_last_four: Optional[str] = Query(None, pattern=r"^\d{4}$"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """Search for borrower profiles.
    
    Supports filtering by name (partial match), SSN last 4, and confidence threshold.
    """
    # Build filters
    filters = []
    
    # Note: This is a simplified implementation
    # In production, use proper database indexing and search
    
    results = await db.query(
        "extraction_results",
        filters=filters,
        page=page,
        page_size=page_size
    )
    
    return {
        "results": results.items,
        "total": results.total_count,
        "page": results.page,
        "page_size": results.page_size
    }


@router.get("/borrowers/{submission_id}")
async def get_borrower_profile(submission_id: str):
    """Get complete borrower profile for a submission."""
    result = await db.read("extraction_results", submission_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Borrower profile not found")
    
    return result


@router.get("/documents/{submission_id}/provenance")
async def get_document_provenance(submission_id: str):
    """Get provenance information for all extracted fields.
    
    Returns source pages, verbatim text snippets, and confidence scores
    for audit and verification purposes.
    """
    result = await db.read("extraction_results", submission_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Extract provenance from result
    # This would traverse the nested structure to find all Provenance objects
    
    return {
        "submission_id": submission_id,
        "provenance": result.get("provenance", {})
    }
```

## Deliverables
- [ ] api/main.py with FastAPI app factory
- [ ] api/routes/health.py with /health and /ready endpoints
- [ ] api/routes/ingestion.py with /upload and /submissions/{id} endpoints
- [ ] api/routes/query.py with /borrowers/search and /borrowers/{id} endpoints
- [ ] Proper HTTP status codes (202 for async acceptance)
- [ ] Global exception handling
- [ ] CORS middleware configured
- [ ] Idempotency via SHA-256 hashing

## Success Criteria
- `POST /api/v1/upload` accepts multipart file uploads
- Returns 202 Accepted with submission_id
- Duplicate files detected via hash and return existing submission
- `GET /api/v1/submissions/{id}` returns submission status
- All endpoints have proper OpenAPI documentation
- Error responses follow standard format

## Testing Snippets
```python
# Test upload
curl -X POST http://localhost:8000/api/v1/upload \
  -F "files=@test.pdf" \
  -F "document_type=loan_application"

# Test query
curl http://localhost:8000/api/v1/borrowers/{submission_id}
```

## Next Prompt
After this completes, move to `08_processing_graph.md` for Pydantic Graph state machine.
