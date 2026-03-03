"""Models for document submission and processing events."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class SubmissionStatus(str, Enum):
    """Processing status for document submissions."""

    PENDING = "pending"
    VALIDATING = "validating"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    VALIDATING_OUTPUT = "validating_output"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class DocumentType(str, Enum):
    """Supported document types."""

    LOAN_APPLICATION = "loan_application"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN = "tax_return"
    PAY_STUB = "pay_stub"
    W2 = "w2"
    ID_DOCUMENT = "id_document"
    UNKNOWN = "unknown"


class DocumentMetadata(BaseModel):
    """Metadata about an uploaded document."""

    document_id: str = Field(..., description="Unique document ID")
    file_hash: str = Field(..., description="SHA-256 hash for idempotency")
    file_name: str = Field(..., description="Original file name")
    file_size: int = Field(..., gt=0, description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    page_count: int | None = Field(None, description="Number of pages (for PDFs)")
    document_type: DocumentType = Field(default=DocumentType.UNKNOWN)
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentSubmission(BaseModel):
    """Complete submission with metadata and processing status."""

    submission_id: str = Field(..., description="Unique submission ID")
    status: SubmissionStatus = Field(default=SubmissionStatus.PENDING)
    documents: list[DocumentMetadata] = Field(default_factory=list)
    borrower_profile_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None
    processing_metadata: dict = Field(default_factory=dict)


class DocumentUploadedEvent(BaseModel):
    """Event emitted when document is uploaded."""

    submission_id: str
    document_id: str
    file_hash: str
    storage_path: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
