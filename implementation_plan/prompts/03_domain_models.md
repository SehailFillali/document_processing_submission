# Prompt 03: Domain Models - Pydantic Schemas

## Status
[COMPLETED]

## Context
We need to define the core data models for document extraction, focusing on the Loan Documents use case (with extensibility for Construction Submittals).

## Objective
Create Pydantic v2 models for BorrowerProfile with strict validation and provenance tracking.

## Requirements

### 1. Create Base Domain Model
File: `src/doc_extract/domain/base.py`

```python
"""Base domain models with common fields and mixins."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class DomainModel(BaseModel):
    """Base model for all domain entities."""
    
    model_config = ConfigDict(
        strict=True,
        validate_assignment=True,
        extra="forbid",
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Provenance(BaseModel):
    """Tracks the source of extracted data for auditability."""
    
    source_document: str = Field(..., description="Original document ID or path")
    source_page: int | None = Field(None, description="Page number where data was found")
    verbatim_text: str | None = Field(None, description="Original text snippet")
    confidence_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Confidence score from 0.0 to 1.0"
    )
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)


class MissingField(BaseModel):
    """Explicit type for missing data with reason."""
    
    field_name: str
    reason: str = Field(..., description="Why the field is missing")
    is_critical: bool = Field(default=False, description="Whether missing this field is a critical error")
```

### 2. Create Borrower Profile Models
File: `src/doc_extract/domain/borrower.py`

```python
"""Domain models for loan document extraction."""
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from doc_extract.domain.base import DomainModel, Provenance, MissingField


class Address(BaseModel):
    """Physical address with validation."""
    
    street: str = Field(..., min_length=1, description="Street address")
    city: str = Field(..., min_length=1, description="City")
    state: str = Field(..., min_length=2, max_length=2, description="State code (2 letters)")
    zip_code: str = Field(..., pattern=r"^\d{5}(-\d{4})?$", description="ZIP code")
    country: str = Field(default="US", description="Country code")
    
    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Normalize state to uppercase."""
        return v.upper()


class IncomeEntry(BaseModel):
    """Single income entry with provenance."""
    
    amount: float = Field(..., gt=0, description="Income amount")
    period_start: date = Field(..., description="Start of reporting period")
    period_end: date = Field(..., description="End of reporting period")
    source: str = Field(..., description="Income source (employer, self-employed, etc.)")
    provenance: Provenance
    
    @field_validator("period_end")
    @classmethod
    def validate_period(cls, end: date, info) -> date:
        """Ensure period_end is after period_start."""
        start = info.data.get("period_start")
        if start and end <= start:
            raise ValueError("period_end must be after period_start")
        return end


class AccountInfo(BaseModel):
    """Loan or account information."""
    
    account_number: str = Field(..., min_length=1, description="Account/loan number")
    account_type: str = Field(..., description="Type of account/loan")
    institution: str | None = Field(None, description="Financial institution name")
    open_date: date | None = Field(None, description="Account open date")
    current_balance: float | None = Field(None, description="Current balance")
    provenance: Provenance


class BorrowerProfile(DomainModel):
    """Complete borrower profile extracted from documents."""
    
    # Identity
    borrower_id: str = Field(..., description="Unique borrower identifier")
    name: str = Field(..., min_length=1, description="Borrower full name")
    ssn_last_four: str | None = Field(
        None, 
        pattern=r"^\d{4}$",
        description="Last 4 digits of SSN for verification"
    )
    
    # Contact
    address: Address | MissingField
    phone: str | None = Field(None, pattern=r"^\d{10}$", description="Phone number (digits only)")
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address")
    
    # Financial
    income_history: list[IncomeEntry] = Field(default_factory=list)
    accounts: list[AccountInfo] = Field(default_factory=list)
    
    # Metadata
    source_documents: list[str] = Field(
        default_factory=list,
        description="List of document IDs/sources where this data was extracted"
    )
    extraction_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence score across all fields"
    )
    
    # Validation flags
    validation_errors: list[str] = Field(default_factory=list)
    requires_manual_review: bool = Field(default=False)
    
    @field_validator("income_history")
    @classmethod
    def validate_income_history(cls, v: list[IncomeEntry]) -> list[IncomeEntry]:
        """Ensure income history is not empty for valid profiles."""
        # Note: We allow empty during extraction, but flag it
        return v
    
    def calculate_overall_confidence(self) -> float:
        """Calculate weighted average confidence from all provenance fields."""
        confidences = []
        
        # Collect all provenance confidence scores
        for income in self.income_history:
            confidences.append(income.provenance.confidence_score)
        
        for account in self.accounts:
            confidences.append(account.provenance.confidence_score)
        
        if not confidences:
            return 0.0
        
        return sum(confidences) / len(confidences)


class ExtractionResult(BaseModel):
    """Result of document extraction with partial success support."""
    
    submission_id: str = Field(..., description="Unique submission identifier")
    status: str = Field(..., pattern=r"^(success|partial|failed|pending)$")
    borrower_profile: BorrowerProfile | None = None
    errors: list[dict] = Field(default_factory=list)
    processing_time_seconds: float | None = None
    token_usage: dict | None = None  # For cost tracking
```

### 3. Create Submission/Event Models
File: `src/doc_extract/domain/submission.py`

```python
"""Models for document submission and processing events."""
from datetime import datetime
from enum import Enum
from typing import Optional
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
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentSubmission(BaseModel):
    """Complete submission with metadata and processing status."""
    
    submission_id: str = Field(..., description="Unique submission ID")
    status: SubmissionStatus = Field(default=SubmissionStatus.PENDING)
    documents: list[DocumentMetadata] = Field(default_factory=list)
    borrower_profile_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error_message: str | None = None
    processing_metadata: dict = Field(default_factory=dict)


class DocumentUploadedEvent(BaseModel):
    """Event emitted when document is uploaded."""
    
    submission_id: str
    document_id: str
    file_hash: str
    storage_path: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### 4. Create Validation Models
File: `src/doc_extract/domain/validation.py`

```python
"""Validation rules and results for extracted data."""
from pydantic import BaseModel, Field
from typing import Any


class ValidationRule(BaseModel):
    """A single validation rule."""
    
    rule_id: str
    field_path: str  # e.g., "borrower.income_history[0].amount"
    rule_type: str  # e.g., "range", "format", "required"
    condition: str  # Human-readable condition
    severity: str = Field(default="error", pattern=r"^(error|warning|info)$")


class ValidationResult(BaseModel):
    """Result of applying validation rules."""
    
    rule_id: str
    passed: bool
    field_path: str
    actual_value: Any | None = None
    expected_condition: str
    message: str
    severity: str


class ValidationReport(BaseModel):
    """Complete validation report for a submission."""
    
    submission_id: str
    passed: bool
    results: list[ValidationResult]
    error_count: int = 0
    warning_count: int = 0
    requires_manual_review: bool = False
```

## Deliverables
- [ ] domain/base.py with DomainModel, Provenance, MissingField
- [ ] domain/borrower.py with BorrowerProfile, IncomeEntry, AccountInfo
- [ ] domain/submission.py with SubmissionStatus, DocumentMetadata
- [ ] domain/validation.py with ValidationRule, ValidationReport
- [ ] All models have strict validation and negative space assertions
- [ ] Provenance tracking implemented on all extracted fields

## Success Criteria
- All Pydantic models validate correctly
- Field validators reject invalid data (e.g., negative income, invalid dates)
- Provenance model captures source tracking requirements
- MissingField type supports explicit missing data handling

## Code Snippets to Include
All files above are complete and production-ready.

## Next Prompt
After this completes, move to `04_ports_interfaces.md` for Hexagonal Architecture ports.
