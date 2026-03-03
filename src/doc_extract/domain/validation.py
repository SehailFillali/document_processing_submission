"""Validation rules and results for extracted data."""

from typing import Any

from pydantic import BaseModel, Field


class ValidationRule(BaseModel):
    """A single validation rule."""

    rule_id: str
    field_path: str
    rule_type: str
    condition: str
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
