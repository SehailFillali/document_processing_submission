"""Tests for domain models."""

from datetime import date

import pytest
from pydantic import ValidationError

from doc_extract.domain.base import MissingField, Provenance
from doc_extract.domain.borrower import Address, BorrowerProfile, IncomeEntry
from doc_extract.domain.submission import (
    DocumentMetadata,
    DocumentType,
    SubmissionStatus,
)


class TestProvenance:
    """Tests for Provenance model."""

    def test_valid_provenance(self):
        """Test creating valid provenance."""
        prov = Provenance(
            source_document="doc1.pdf",
            source_page=1,
            verbatim_text="Test text",
            confidence_score=0.85,
        )
        assert prov.source_document == "doc1.pdf"
        assert prov.confidence_score == 0.85

    def test_confidence_bounds(self):
        """Test confidence score validation."""
        with pytest.raises(ValidationError):
            Provenance(
                source_document="doc1.pdf",
                confidence_score=1.5,  # Too high
            )

        with pytest.raises(ValidationError):
            Provenance(
                source_document="doc1.pdf",
                confidence_score=-0.1,  # Too low
            )


class TestAddress:
    """Tests for Address model."""

    def test_valid_address(self):
        """Test creating valid address."""
        addr = Address(
            street="123 Main St",
            city="Boston",
            state="MA",
            zip_code="02101",
        )
        assert addr.state == "MA"
        assert addr.country == "US"

    def test_state_normalization(self):
        """Test state is normalized to uppercase."""
        addr = Address(
            street="123 Main St",
            city="Boston",
            state="ma",
            zip_code="02101",
        )
        assert addr.state == "MA"

    def test_invalid_zip(self):
        """Test invalid ZIP code."""
        with pytest.raises(ValidationError):
            Address(
                street="123 Main St",
                city="Boston",
                state="MA",
                zip_code="invalid",
            )


class TestBorrowerProfile:
    """Tests for BorrowerProfile model."""

    def test_valid_profile(self):
        """Test creating valid borrower profile."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=Address(
                street="123 Main St",
                city="Boston",
                state="MA",
                zip_code="02101",
            ),
        )
        assert profile.borrower_id == "123"
        assert profile.name == "John Doe"

    def test_ssn_validation(self):
        """Test SSN last four validation."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=Address(
                street="123 Main St",
                city="Boston",
                state="MA",
                zip_code="02101",
            ),
            ssn_last_four="1234",
        )
        assert profile.ssn_last_four == "1234"

        with pytest.raises(ValidationError):
            BorrowerProfile(
                borrower_id="123",
                name="John Doe",
                address=Address(
                    street="123 Main St",
                    city="Boston",
                    state="MA",
                    zip_code="02101",
                ),
                ssn_last_four="123",  # Too short
            )

    def test_missing_field(self):
        """Test missing field handling."""
        profile = BorrowerProfile(
            borrower_id="123",
            name="John Doe",
            address=MissingField(
                field_name="address",
                reason="Not provided in document",
                is_critical=True,
            ),
        )
        assert isinstance(profile.address, MissingField)


class TestIncomeEntry:
    """Tests for IncomeEntry model."""

    def test_valid_income(self):
        """Test creating valid income entry."""
        income = IncomeEntry(
            amount=5000.00,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            source="Acme Corp",
            provenance=Provenance(
                source_document="paystub.pdf",
                confidence_score=0.9,
            ),
        )
        assert income.amount == 5000.0

    def test_period_validation(self):
        """Test period end must be after start."""
        with pytest.raises(ValidationError):
            IncomeEntry(
                amount=5000.00,
                period_start=date(2024, 12, 31),
                period_end=date(2024, 1, 1),  # Before start
                source="Acme Corp",
                provenance=Provenance(
                    source_document="paystub.pdf",
                    confidence_score=0.9,
                ),
            )

    def test_negative_income(self):
        """Test negative income is rejected."""
        with pytest.raises(ValidationError):
            IncomeEntry(
                amount=-1000.00,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
                source="Acme Corp",
                provenance=Provenance(
                    source_document="paystub.pdf",
                    confidence_score=0.9,
                ),
            )


class TestDocumentMetadata:
    """Tests for DocumentMetadata model."""

    def test_valid_document(self):
        """Test creating valid document metadata."""
        doc = DocumentMetadata(
            document_id="doc-123",
            file_hash="abc123",
            file_name="loan.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        assert doc.document_id == "doc-123"
        assert doc.document_type == DocumentType.UNKNOWN

    def test_document_type(self):
        """Test document type enum."""
        doc = DocumentMetadata(
            document_id="doc-123",
            file_hash="abc123",
            file_name="loan.pdf",
            file_size=1024,
            mime_type="application/pdf",
            document_type=DocumentType.LOAN_APPLICATION,
        )
        assert doc.document_type == DocumentType.LOAN_APPLICATION


class TestSubmissionStatus:
    """Tests for SubmissionStatus enum."""

    def test_status_values(self):
        """Test enum values."""
        assert SubmissionStatus.PENDING.value == "pending"
        assert SubmissionStatus.COMPLETED.value == "completed"
        assert SubmissionStatus.FAILED.value == "failed"
