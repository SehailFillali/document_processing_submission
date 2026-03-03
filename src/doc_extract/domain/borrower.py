"""Domain models for loan document extraction."""

import re
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from doc_extract.domain.base import DomainModel, MissingField, Provenance


# Sentinel strings the LLM uses to mean "no value found"
_NULL_SENTINELS = frozenset(
    {"not found", "not specified", "n/a", "unknown", "none", "null", ""}
)


def _is_null_sentinel(v: str) -> bool:
    """Return True if the string is one of the LLM's null placeholders."""
    return v.strip().lower() in _NULL_SENTINELS


def _coerce_date(v: object) -> object:
    """Parse common date formats that the LLM returns."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v
    # BUG-1 fix: LLM sometimes returns a bare integer year (e.g. 2024)
    if isinstance(v, (int, float)):
        year = int(v)
        if 2000 <= year <= 2099:
            return date(year, 1, 1)
        return None
    if isinstance(v, str):
        v = v.strip()
        if _is_null_sentinel(v):
            return None
        # Bare year string like "2024"
        if v.isdigit() and len(v) == 4:
            year = int(v)
            if 2000 <= year <= 2099:
                return date(year, 1, 1)
            return None
        # Try common date formats including 2-digit year (BUG-2 fix)
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%y", "%m-%d-%y"):
            try:
                return datetime.strptime(v, fmt).date()
            except ValueError:
                continue
    return v


class Address(BaseModel):
    """Physical address with validation."""

    street: str = Field(..., min_length=1, description="Street address")
    city: str = Field(..., min_length=1, description="City")
    state: str = Field(
        ..., min_length=2, max_length=2, description="State code (2 letters)"
    )
    zip_code: str = Field(..., pattern=r"^\d{5}(-\d{4})?$", description="ZIP code")
    country: str = Field(default="US", description="Country code")

    @field_validator("country", mode="before")
    @classmethod
    def default_country(cls, v: str | None) -> str:
        """Default country to US when LLM returns null."""
        return v or "US"

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Normalize state to uppercase."""
        return v.upper()


class IncomeEntry(BaseModel):
    """Single income entry with provenance."""

    amount: float = Field(..., ge=0, description="Income amount")
    period_start: date | None = Field(None, description="Start of reporting period")
    period_end: date | None = Field(None, description="End of reporting period")
    source: str = Field(
        ..., description="Income source (employer, self-employed, etc.)"
    )
    provenance: Provenance | None = Field(None, description="Source provenance")

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def coerce_date_formats(cls, v: object) -> object:
        """Parse common date formats and convert invalid values to None."""
        return _coerce_date(v)

    @field_validator("period_end")
    @classmethod
    def validate_period(cls, end: date | None, info) -> date | None:
        """Ensure period_end is after period_start when both are present."""
        start = info.data.get("period_start")
        if start and end and end <= start:
            raise ValueError("period_end must be after period_start")
        return end


class AccountInfo(BaseModel):
    """Loan or account information."""

    account_number: str | None = Field(None, description="Account/loan number")
    account_type: str = Field(..., description="Type of account/loan")
    institution: str | None = Field(None, description="Financial institution name")
    open_date: date | None = Field(None, description="Account open date")
    current_balance: float | None = Field(None, description="Current balance")
    provenance: Provenance | None = Field(None, description="Source provenance")

    @field_validator("open_date", mode="before")
    @classmethod
    def coerce_date_formats(cls, v: object) -> object:
        """Parse common date formats and convert invalid values to None."""
        return _coerce_date(v)


class BorrowerProfile(DomainModel):
    """Complete borrower profile extracted from documents."""

    # Identity - made optional for partial extraction
    borrower_id: str | None = Field(None, description="Unique borrower identifier")
    name: str | None = Field(None, min_length=1, description="Borrower full name")
    name_provenance: Provenance | None = Field(
        None, description="Source document reference for borrower name"
    )
    ssn_last_four: str | None = Field(
        None, pattern=r"^\d{4}$", description="Last 4 digits of SSN for verification"
    )

    @field_validator("ssn_last_four", mode="before")
    @classmethod
    def coerce_ssn_null(cls, v: str | None) -> str | None:
        """Convert LLM null-sentinel strings to None for optional SSN."""
        if v is None:
            return None
        if isinstance(v, str) and _is_null_sentinel(v):
            return None
        return v

    # Contact - made optional
    address: Address | MissingField | None = Field(None)
    address_provenance: Provenance | None = Field(
        None, description="Source document reference for address"
    )
    phone: str | None = Field(None, description="Phone number (digits only)")
    email: str | None = Field(None, description="Email address")

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        """Validate email format or convert non-email strings to None."""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if _is_null_sentinel(v):
                return None
            if "@" not in v:
                return None
        return v

    # Financial
    income_history: list[IncomeEntry] = Field(default_factory=list)
    accounts: list[AccountInfo] = Field(default_factory=list)

    # Metadata
    source_documents: list[str] = Field(
        default_factory=list,
        description="List of document IDs/sources where this data was extracted",
    )
    extraction_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence score across all fields",
    )

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def default_confidence(cls, v: object) -> object:
        """Default null confidence to 0.0."""
        if v is None:
            return 0.0
        if isinstance(v, str) and _is_null_sentinel(v):
            return 0.0
        return v

    # Validation flags
    validation_errors: list[str] = Field(default_factory=list)
    requires_manual_review: bool = Field(default=False)

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        """Strip non-digit characters from phone numbers."""
        if v is None:
            return None
        digits = re.sub(r"\D", "", v)
        return digits if digits else None

    @field_validator("income_history")
    @classmethod
    def validate_income_history(cls, v: list[IncomeEntry]) -> list[IncomeEntry]:
        """Ensure income history is not empty for valid profiles."""
        return v

    def calculate_overall_confidence(self) -> float:
        """Calculate weighted average confidence from all provenance fields."""
        confidences = []

        if self.name_provenance:
            confidences.append(self.name_provenance.confidence_score)

        if self.address_provenance:
            confidences.append(self.address_provenance.confidence_score)

        for income in self.income_history:
            if income.provenance:
                confidences.append(income.provenance.confidence_score)

        for account in self.accounts:
            if account.provenance:
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
    token_usage: dict | None = None
