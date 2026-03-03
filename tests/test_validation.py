"""Tests for validation domain models."""

import pytest
from pydantic import ValidationError

from doc_extract.domain.validation import (
    ValidationReport,
    ValidationResult,
    ValidationRule,
)


class TestValidationRule:
    """Tests for ValidationRule model."""

    def test_valid_rule(self):
        """Test creating valid validation rule."""
        rule = ValidationRule(
            rule_id="rule-001",
            field_path="borrower.name",
            rule_type="required",
            condition="name is not empty",
            severity="error",
        )
        assert rule.rule_id == "rule-001"
        assert rule.severity == "error"

    def test_rule_warning_severity(self):
        """Test rule with warning severity."""
        rule = ValidationRule(
            rule_id="rule-001",
            field_path="borrower.name",
            rule_type="required",
            condition="name is not empty",
            severity="warning",
        )
        assert rule.severity == "warning"

    def test_rule_info_severity(self):
        """Test rule with info severity."""
        rule = ValidationRule(
            rule_id="rule-001",
            field_path="borrower.name",
            rule_type="required",
            condition="name is not empty",
            severity="info",
        )
        assert rule.severity == "info"

    def test_severity_validation(self):
        """Test severity enum validation."""
        with pytest.raises(ValidationError):
            ValidationRule(
                rule_id="rule-001",
                field_path="borrower.name",
                rule_type="required",
                condition="name is not empty",
                severity="critical",
            )


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_result(self):
        """Test creating valid validation result."""
        result = ValidationResult(
            rule_id="rule-001",
            passed=True,
            field_path="borrower.name",
            actual_value="John",
            expected_condition="not empty",
            message="Field is valid",
            severity="error",
        )
        assert result.passed is True
        assert result.actual_value == "John"

    def test_result_failed(self):
        """Test failed validation result."""
        result = ValidationResult(
            rule_id="rule-001",
            passed=False,
            field_path="borrower.name",
            actual_value="",
            expected_condition="not empty",
            message="Name is required",
            severity="error",
        )
        assert result.passed is False
        assert result.actual_value == ""

    def test_result_without_actual_value(self):
        """Test validation result without actual value."""
        result = ValidationResult(
            rule_id="rule-001",
            passed=False,
            field_path="borrower.name",
            actual_value=None,
            expected_condition="not empty",
            message="Name is required",
            severity="error",
        )
        assert result.actual_value is None


class TestValidationReport:
    """Tests for ValidationReport model."""

    def test_valid_report(self):
        """Test creating valid validation report."""
        results = [
            ValidationResult(
                rule_id="rule-001",
                passed=True,
                field_path="borrower.name",
                expected_condition="not empty",
                message="OK",
                severity="error",
            ),
            ValidationResult(
                rule_id="rule-002",
                passed=False,
                field_path="borrower.address",
                expected_condition="not empty",
                message="Missing address",
                severity="warning",
            ),
        ]

        report = ValidationReport(
            submission_id="sub-123",
            passed=False,
            results=results,
            error_count=1,
            warning_count=1,
            requires_manual_review=True,
        )

        assert report.passed is False
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.requires_manual_review is True

    def test_report_all_passed(self):
        """Test report when all validations pass."""
        results = [
            ValidationResult(
                rule_id="rule-001",
                passed=True,
                field_path="borrower.name",
                expected_condition="not empty",
                message="OK",
                severity="error",
            ),
        ]

        report = ValidationReport(
            submission_id="sub-123",
            passed=True,
            results=results,
            error_count=0,
            warning_count=0,
            requires_manual_review=False,
        )

        assert report.passed is True
        assert report.requires_manual_review is False

    def test_report_empty_results(self):
        """Test report with empty results."""
        report = ValidationReport(
            submission_id="sub-123",
            passed=True,
            results=[],
            error_count=0,
            warning_count=0,
            requires_manual_review=False,
        )

        assert len(report.results) == 0
