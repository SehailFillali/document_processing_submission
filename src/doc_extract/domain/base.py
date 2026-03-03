"""Base domain models with common fields and mixins."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DomainModel(BaseModel):
    """Base model for all domain entities."""

    model_config = ConfigDict(
        strict=False,
        validate_assignment=True,
        extra="forbid",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def coerce_none_datetime(cls, v: object) -> object:
        """Convert None, string 'None', or empty strings to current UTC time."""
        if v is None:
            return datetime.now(UTC)
        if isinstance(v, str) and v.strip().lower() in ("none", "", "n/a"):
            return datetime.now(UTC)
        return v


class Provenance(BaseModel):
    """Tracks the source of extracted data for auditability."""

    source_document: str = Field(..., description="Original document ID or path")
    source_page: int | None = Field(
        None, description="Page number where data was found"
    )
    verbatim_text: str | None = Field(None, description="Original text snippet")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0"
    )
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MissingField(BaseModel):
    """Explicit type for missing data with reason."""

    field_name: str
    reason: str = Field(..., description="Why the field is missing")
    is_critical: bool = Field(
        default=False, description="Whether missing this field is a critical error"
    )
