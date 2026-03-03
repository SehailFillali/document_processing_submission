"""Tests for utilities and services."""


import pytest

from doc_extract.services.processing import ProcessingService
from doc_extract.utils.hashing import (
    compute_file_hash,
    generate_document_id,
    generate_submission_id,
    generate_trace_id,
)


class TestHashingUtils:
    """Tests for hashing utilities."""

    def test_generate_submission_id(self):
        """Test submission ID generation."""
        id1 = generate_submission_id()
        id2 = generate_submission_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID format

    def test_generate_document_id(self):
        """Test document ID generation."""
        id1 = generate_document_id()
        id2 = generate_document_id()
        assert id1 != id2

    def test_compute_file_hash(self):
        """Test file hash computation."""
        hash1 = compute_file_hash(b"test content")
        hash2 = compute_file_hash(b"test content")
        hash3 = compute_file_hash(b"different content")

        assert hash1 == hash2  # Same content = same hash
        assert hash1 != hash3  # Different content = different hash
        assert len(hash1) == 64  # SHA-256 hex length

    def test_generate_trace_id(self):
        """Test trace ID generation."""
        trace1 = generate_trace_id()
        trace2 = generate_trace_id()
        assert trace1 != trace2
        assert "-" in trace1  # Contains timestamp-uuid format


class TestProcessingService:
    """Tests for ProcessingService."""

    @pytest.fixture
    def service(self):
        """Create processing service."""
        return ProcessingService()

    @pytest.mark.asyncio
    async def test_validate_extraction_valid(self, service):
        """Test validation with valid data."""
        result = await service.validate_extraction(
            {
                "name": "John Doe",
                "address": {"street": "123 Main St"},
                "income_history": [{"amount": 5000}],
            }
        )

        assert result["passed"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_extraction_missing_name(self, service):
        """Test validation with missing name."""
        result = await service.validate_extraction(
            {
                "address": {"street": "123 Main St"},
                "income_history": [],
            }
        )

        assert result["passed"] is False
        assert "Missing borrower name" in result["errors"]

    @pytest.mark.asyncio
    async def test_validate_extraction_missing_address(self, service):
        """Test validation with missing address."""
        result = await service.validate_extraction(
            {
                "name": "John Doe",
                "income_history": [],
            }
        )

        assert result["passed"] is False
        assert "Missing address" in result["errors"]

    @pytest.mark.asyncio
    async def test_validate_extraction_missing_income(self, service):
        """Test validation with missing income history."""
        result = await service.validate_extraction(
            {
                "name": "John Doe",
                "address": {"street": "123 Main St"},
            }
        )

        assert result["passed"] is False
        assert "Missing income history" in result["errors"]
