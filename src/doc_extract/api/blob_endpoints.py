"""Blob storage endpoints for processing files from S3/GCS/MinIO."""

import hashlib
import json
import uuid
from io import BytesIO

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.storage_factory import get_storage_adapter
from doc_extract.core.config import settings
from doc_extract.core.logging import logger
from doc_extract.domain.submission import (
    DocumentMetadata,
    DocumentType,
    SubmissionStatus,
)
from doc_extract.services.processing import ProcessingService

router = APIRouter(prefix="/api/v1", tags=["Blob Storage"])


class BlobUriRequest(BaseModel):
    """Request to process a document from blob storage URI."""

    uri: str = Field(
        ...,
        description="Blob storage URI (minio://bucket/path, s3://bucket/path, gs://bucket/path)",
    )
    document_type: str = Field(
        default="loan_application", description="Type of document being processed"
    )
    borrower_id: str | None = Field(
        default=None, description="Optional borrower ID for tracking"
    )


class BlobProcessingResponse(BaseModel):
    """Response for blob storage processing request."""

    submission_id: str
    status: str
    message: str
    uri: str


@router.post("/documents/process_uploaded_blob", response_model=BlobProcessingResponse)
async def process_from_blob(request: BlobUriRequest):
    """Process a document from blob storage (S3, GCS, MinIO).

    The system will:
    1. Connect to the blob storage using the URI scheme
    2. Download the document
    3. Process it using the extraction pipeline
    4. Return the submission ID for tracking

    Supported URI schemes:
    - minio://bucket/object - Local MinIO
    - s3://bucket/object   - AWS S3
    - gs://bucket/object  - Google Cloud Storage

    Example:
        minio://documents/loan-app-123.pdf
        s3://my-bucket/invoices/2024/abc.pdf
        gs://project-bucket/loan-docs/def.pdf
    """
    try:
        uri = request.uri
        if not uri or "://" not in uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid blob URI. Must include scheme (minio://, s3://, gs://)",
            )

        storage = get_storage_adapter()

        if not await storage.exists(uri):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found at URI: {uri}",
            )

        metadata = await storage.get_metadata(uri)
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not retrieve metadata for: {uri}",
            )

        content = await storage.download(uri)

        submission_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())

        file_hash = hashlib.sha256(content).hexdigest()

        doc_metadata = DocumentMetadata(
            document_id=document_id,
            file_hash=file_hash,
            file_name=uri.split("/")[-1],
            file_size=len(content),
            mime_type=metadata.content_type,
            document_type=DocumentType(request.document_type),
        )

        from doc_extract.api.main import db

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
                        "source_uri": uri,
                        "document_type": request.document_type,
                        "borrower_id": request.borrower_id,
                    }
                ),
            },
        )

        extraction_status = SubmissionStatus.PROCESSING

        try:
            temp_storage = LocalFileSystemAdapter(base_path="./uploads")
            temp_path = f"{submission_id}/{document_id}_{doc_metadata.file_name}"
            await temp_storage.upload(
                BytesIO(content),
                temp_path,
                content_type=metadata.content_type,
            )

            processor = ProcessingService()
            result = await processor.process_submission(submission_id, temp_path)

            if result.get("status") == "success":
                extraction_status = SubmissionStatus.COMPLETED
                profile_id = str(uuid.uuid4())
                borrower_data = result.get("data")

                await db.create(
                    "borrower_profiles",
                    {
                        "id": profile_id,
                        "borrower_id": submission_id,
                        "data": json.dumps(borrower_data, default=str),
                    },
                )

                await db.update(
                    "submissions",
                    submission_id,
                    {
                        "status": extraction_status.value,
                        "borrower_profile_id": profile_id,
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
            await db.update(
                "submissions",
                submission_id,
                {
                    "status": extraction_status.value,
                    "error_message": str(e),
                },
            )

        logger.info(f"Blob document processed: {submission_id}")

        return BlobProcessingResponse(
            submission_id=submission_id,
            status=extraction_status.value,
            message=f"Document from {uri} processed successfully",
            uri=uri,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blob processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        ) from e


@router.get("/blob/health")
async def blob_storage_health():
    """Check blob storage connectivity."""
    try:
        storage = get_storage_adapter()
        if hasattr(storage, "client") and storage.client is not None:
            storage.client.list_buckets()
            return {
                "status": "healthy",
                "backend": settings.storage_backend,
                "endpoint": settings.minio_endpoint,
                "bucket": settings.minio_bucket_name,
            }
        return {"status": "unknown", "backend": settings.storage_backend}
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "backend": settings.storage_backend,
        }
