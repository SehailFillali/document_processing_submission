"""API response schemas including standardized error format."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional error context"
    )
    retry_after: float | None = Field(
        None, description="Seconds to wait before retrying"
    )


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error: ErrorDetail

    @classmethod
    def from_exception(cls, exc: Exception) -> "ErrorResponse":
        """Create error response from exception."""
        if hasattr(exc, "to_dict"):
            data = exc.to_dict()
            return cls(**data)

        return cls(
            error=ErrorDetail(code="INTERNAL_UNEXPECTED_ERROR", message=str(exc))
        )


class SuccessResponse(BaseModel):
    """Standard success response."""

    data: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel):
    """Paginated response."""

    data: list[dict[str, Any]]
    pagination: dict[str, Any] = Field(..., description="Pagination metadata")
