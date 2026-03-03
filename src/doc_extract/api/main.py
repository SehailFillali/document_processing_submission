"""FastAPI main application and routes."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.sqlite_adapter import SQLiteAdapter
from doc_extract.api.blob_endpoints import router as blob_router
from doc_extract.api.observability_endpoints import router as obs_router
from doc_extract.api.resilience_endpoints import router as resilience_router
from doc_extract.core.error_codes import ErrorCode, get_status_for_error_code
from doc_extract.core.exceptions import DocExtractError
from doc_extract.core.logging import logger, setup_logging
from doc_extract.core.observability import obs_config
from doc_extract.core.prometheus import PrometheusMiddleware, metrics_router
from doc_extract.core.rate_limiter import RateLimitMiddleware
from doc_extract.domain.submission import (
    DocumentMetadata,
    DocumentType,
    SubmissionStatus,
)

setup_logging()

app = FastAPI(
    title="Document Extraction API",
    description="API for extracting structured data from unstructured documents",
    version="0.1.0",
)

app.include_router(blob_router)
app.include_router(obs_router)
app.include_router(resilience_router)
app.include_router(metrics_router)

app.add_middleware(PrometheusMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(DocExtractError)
async def doc_extract_exception_handler(request: Request, exc: DocExtractError):
    """Handle custom application exceptions with structured error codes."""
    status_code = get_status_for_error_code(exc.error_code)

    logger.error(
        f"Error {exc.error_code.value}: {exc.message}", extra={"details": exc.details}
    )

    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after))

    return JSONResponse(status_code=status_code, content=exc.to_dict(), headers=headers)


storage = LocalFileSystemAdapter(base_path="./uploads")
db = SQLiteAdapter()


class SubmissionResponse(BaseModel):
    submission_id: str
    status: str
    message: str


class QueryResponse(BaseModel):
    submission_id: str
    status: str
    borrower_profile: dict | None = None
    error_message: str | None = None


@app.on_event("startup")
async def startup():
    """Initialize application on startup."""
    Path("./uploads").mkdir(exist_ok=True)
    await db.init_tables()
    obs_config.initialize_logfire()
    logger.info("Document Extraction API started (SQLite persistence enabled)")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}


@app.post("/api/v1/documents/upload", response_model=SubmissionResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "loan_application",
):
    """Upload a document for processing."""
    try:
        file_hash = hashlib.sha256()
        content = await file.read()
        file_hash.update(content)
        file_hash_str = file_hash.hexdigest()

        document_id = str(uuid.uuid4())
        submission_id = str(uuid.uuid4())

        storage_path = f"{submission_id}/{document_id}_{file.filename}"

        from io import BytesIO

        await storage.upload(
            BytesIO(content),
            storage_path,
            content_type=file.content_type,
        )

        doc_metadata = DocumentMetadata(
            document_id=document_id,
            file_hash=file_hash_str,
            file_name=file.filename,
            file_size=len(content),
            mime_type=file.content_type or "application/octet-stream",
            document_type=DocumentType(document_type),
        )

        # Persist submission to SQLite
        await db.create(
            "submissions",
            {
                "id": submission_id,
                "submission_id": submission_id,
                "status": SubmissionStatus.PROCESSING.value,
                "documents": json.dumps([doc_metadata.model_dump(mode="json")]),
                "borrower_profile_id": None,
                "error_message": None,
                "processing_metadata": json.dumps(
                    {
                        "storage_path": storage_path,
                        "file_hash": file_hash_str,
                        "document_type": document_type,
                    }
                ),
            },
        )

        # Trigger processing
        extraction_status = SubmissionStatus.PROCESSING
        borrower_data = None
        error_msg = None

        try:
            from doc_extract.services.processing import ProcessingService

            processor = ProcessingService()
            result = await processor.process_submission(submission_id, storage_path)

            if result.get("status") == "success":
                extraction_status = SubmissionStatus.COMPLETED
                borrower_data = result.get("data")

                # Persist borrower profile to SQLite
                profile_id = str(uuid.uuid4())
                await db.create(
                    "borrower_profiles",
                    {
                        "id": profile_id,
                        "borrower_id": submission_id,
                        "data": json.dumps(borrower_data, default=str),
                    },
                )

                # Update submission with profile reference
                await db.update(
                    "submissions",
                    submission_id,
                    {
                        "status": extraction_status.value,
                        "borrower_profile_id": profile_id,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "processing_metadata": json.dumps(
                            {
                                "storage_path": storage_path,
                                "file_hash": file_hash_str,
                                "document_type": document_type,
                                "confidence": result.get("confidence"),
                                "qa_score": result.get("qa_score"),
                                "retry_count": result.get("retry_count"),
                                "processing_time": result.get("processing_time"),
                            }
                        ),
                    },
                )
            else:
                extraction_status = SubmissionStatus.FAILED
                error_msg = result.get("error", "Processing failed")
                await db.update(
                    "submissions",
                    submission_id,
                    {
                        "status": extraction_status.value,
                        "error_message": error_msg,
                    },
                )
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            extraction_status = SubmissionStatus.FAILED
            error_msg = str(e)
            await db.update(
                "submissions",
                submission_id,
                {
                    "status": extraction_status.value,
                    "error_message": error_msg,
                },
            )

        logger.info(f"Document uploaded: {submission_id} ({extraction_status.value})")

        return SubmissionResponse(
            submission_id=submission_id,
            status=extraction_status.value,
            message=f"Document processed: {extraction_status.value}",
        )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}",
        ) from e


@app.get("/api/v1/submissions/{submission_id}", response_model=QueryResponse)
async def get_submission(submission_id: str):
    """Get submission status and extracted data."""
    row = await db.read("submissions", submission_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

    # Load borrower profile if available
    borrower_profile = None
    profile_id = row.get("borrower_profile_id")
    if profile_id:
        profile_row = await db.read("borrower_profiles", profile_id)
        if profile_row and profile_row.get("data"):
            try:
                borrower_profile = json.loads(profile_row["data"])
            except (json.JSONDecodeError, TypeError):
                borrower_profile = None

    return QueryResponse(
        submission_id=row["submission_id"],
        status=row["status"],
        borrower_profile=borrower_profile,
        error_message=row.get("error_message"),
    )


@app.get("/api/v1/submissions")
async def list_submissions(limit: int = 20):
    """List all submissions."""
    result = await db.query("submissions", order_by="created_at DESC", page_size=limit)
    return {
        "submissions": [
            {
                "submission_id": row["submission_id"],
                "status": row["status"],
                "created_at": row.get("created_at", ""),
            }
            for row in result.items
        ]
    }


@app.get("/api/v1/errors/codes")
async def get_error_codes():
    """Get list of all possible error codes."""
    from doc_extract.core.error_codes import ERROR_CODE_MESSAGES

    return {
        "error_codes": [
            {
                "code": ec.value,
                "description": ERROR_CODE_MESSAGES.get(ec, ""),
                "http_status": get_status_for_error_code(ec),
                "retryable": ec
                in [
                    ErrorCode.LLM_RATE_LIMITED,
                    ErrorCode.LLM_CIRCUIT_OPEN,
                    ErrorCode.RATE_LIMIT_EXCEEDED,
                ],
            }
            for ec in ErrorCode
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
