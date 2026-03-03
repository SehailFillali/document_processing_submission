"""Edge case and property-based tests."""

from datetime import date

import pytest
from pydantic import ValidationError

from doc_extract.domain.base import MissingField, Provenance
from doc_extract.domain.borrower import (
    AccountInfo,
    Address,
    BorrowerProfile,
    IncomeEntry,
)


class TestAddressEdgeCases:
    """Edge case tests for Address."""

    def test_zip_with_extension(self):
        """Test ZIP code with extension."""
        addr = Address(
            street="123 Main St",
            city="Boston",
            state="MA",
            zip_code="02101-1234",
        )
        assert addr.zip_code == "02101-1234"

    def test_state_two_letters_max(self):
        """Test state max length."""
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Boston",
                state="MASS",  # Too long
                zip_code="02101",
            )

    def test_different_states(self):
        """Test various state codes."""
        states = ["CA", "NY", "TX", "FL", "WA"]
        for state in states:
            addr = Address(
                street="123 Main St",
                city="City",
                state=state,
                zip_code="12345",
            )
            assert addr.state == state


class TestBorrowerProfileEdgeCases:
    """Edge case tests for BorrowerProfile."""

    def test_empty_income_history(self):
        """Test profile with empty income history."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(field_name="address", reason="Not found"),
            income_history=[],
        )
        assert profile.income_history == []
        assert profile.calculate_overall_confidence() == 0.0

    def test_multiple_income_entries(self):
        """Test profile with multiple income entries."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.9,
        )

        income1 = IncomeEntry(
            amount=5000,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 6, 30),
            source="Employer 1",
            provenance=prov,
        )

        income2 = IncomeEntry(
            amount=3000,
            period_start=date(2024, 7, 1),
            period_end=date(2024, 12, 31),
            source="Employer 2",
            provenance=prov,
        )

        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(field_name="address", reason="Not found"),
            income_history=[income1, income2],
        )

        assert len(profile.income_history) == 2
        assert profile.calculate_overall_confidence() == 0.9

    def test_multiple_accounts(self):
        """Test profile with multiple accounts."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.85,
        )

        account1 = AccountInfo(
            account_number="123456789",
            account_type="checking",
            institution="Bank A",
            provenance=prov,
        )

        account2 = AccountInfo(
            account_number="987654321",
            account_type="savings",
            institution="Bank B",
            provenance=prov,
        )

        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(field_name="address", reason="Not found"),
            accounts=[account1, account2],
        )

        assert len(profile.accounts) == 2

    def test_validation_errors(self):
        """Test profile with validation errors."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(field_name="address", reason="Not found"),
            validation_errors=["Missing SSN", "Address incomplete"],
        )

        assert len(profile.validation_errors) == 2
        assert profile.requires_manual_review is False  # Not set yet

    def test_requires_manual_review_flag(self):
        """Test manual review flag."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(field_name="address", reason="Not found"),
            requires_manual_review=True,
        )

        assert profile.requires_manual_review is True


class TestProvenanceEdgeCases:
    """Edge case tests for Provenance."""

    def test_provenance_without_page(self):
        """Test provenance when page unknown."""
        prov = Provenance(
            source_document="doc1.pdf",
            source_page=None,
            verbatim_text="Some text",
            confidence_score=0.75,
        )
        assert prov.source_page is None

    def test_provenance_without_verbatim(self):
        """Test provenance when verbatim not available."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.8,
        )
        assert prov.verbatim_text is None

    def test_provenance_full(self):
        """Test provenance with all fields."""
        prov = Provenance(
            source_document="doc1.pdf",
            source_page=5,
            verbatim_text="Exact text from document",
            confidence_score=0.95,
        )

        assert prov.source_document == "doc1.pdf"
        assert prov.source_page == 5
        assert prov.verbatim_text == "Exact text from document"
        assert prov.confidence_score == 0.95

    def test_confidence_zero(self):
        """Test provenance with zero confidence."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.0,
        )
        assert prov.confidence_score == 0.0

    def test_confidence_full(self):
        """Test provenance with full confidence."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=1.0,
        )
        assert prov.confidence_score == 1.0


class TestMissingFieldEdgeCases:
    """Edge case tests for MissingField."""

    def test_critical_missing_field(self):
        """Test critical missing field."""
        mf = MissingField(
            field_name="ssn",
            reason="Not provided",
            is_critical=True,
        )
        assert mf.is_critical is True

    def test_non_critical_missing_field(self):
        """Test non-critical missing field."""
        mf = MissingField(
            field_name="middle_name",
            reason="Optional field",
            is_critical=False,
        )
        assert mf.is_critical is False

    def test_missing_field_default(self):
        """Test missing field default."""
        mf = MissingField(
            field_name="middle_name",
            reason="Optional",
        )
        assert mf.is_critical is False


class TestIncomeEntryEdgeCases:
    """Edge case tests for IncomeEntry."""

    def test_income_same_period(self):
        """Test income entries with same period."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.9,
        )

        income = IncomeEntry(
            amount=10000,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            source="Annual salary",
            provenance=prov,
        )

        assert income.amount == 10000

    def test_zero_amount_allowed(self):
        """Test that zero amount is accepted (LLM uses 0 for unknown amounts)."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.9,
        )

        income = IncomeEntry(
            amount=0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            source="Salary",
            provenance=prov,
        )
        assert income.amount == 0

    def test_negative_amount_not_allowed(self):
        """Test that negative amount is rejected."""
        prov = Provenance(
            source_document="doc1.pdf",
            confidence_score=0.9,
        )

        with pytest.raises(ValidationError):
            IncomeEntry(
                amount=-100,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
                source="Salary",
                provenance=prov,
            )
