"""Tests for processing graph nodes with mocked dependencies."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import End

from doc_extract.domain.base import Provenance
from doc_extract.domain.borrower import Address, BorrowerProfile, IncomeEntry
from doc_extract.services.graph import (
    ExtractNode,
    ExtractState,
    PreprocessNode,
    PreprocessState,
    ValidateNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provenance(**overrides) -> Provenance:
    defaults = {
        "source_document": "test.pdf",
        "source_page": 1,
        "confidence_score": 0.95,
        "verbatim_text": "sample text",
    }
    defaults.update(overrides)
    return Provenance(**defaults)


def _make_income(**overrides) -> IncomeEntry:
    defaults = {
        "amount": 5000.0,
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 1, 31),
        "source": "employment",
        "provenance": _make_provenance(),
    }
    defaults.update(overrides)
    return IncomeEntry(**defaults)


def _make_profile(**overrides) -> BorrowerProfile:
    defaults = {
        "name": "John Doe",
        "address": Address(
            street="123 Main St",
            city="Springfield",
            state="IL",
            zip_code="62701",
            country="US",
        ),
        "income_history": [_make_income()],
        "accounts": [],
    }
    defaults.update(overrides)
    return BorrowerProfile(**defaults)


# ---------------------------------------------------------------------------
# PreprocessNode
# ---------------------------------------------------------------------------


class TestPreprocessNode:
    """Test preprocessing validation node."""

    @pytest.mark.asyncio
    async def test_preprocess_file_exists(self, tmp_path):
        """Happy path: file exists, passes validation."""
        test_file = tmp_path / "sub" / "doc.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_bytes(b"fake pdf content")

        state = PreprocessState(
            submission_id="test-123",
            document_paths=["sub/doc.pdf"],
            validation_passed=True,
        )

        node = PreprocessNode()

        with patch(
            "doc_extract.adapters.local_storage.LocalFileSystemAdapter"
        ) as mock_storage_cls:
            mock_storage = mock_storage_cls.return_value
            mock_storage.exists = AsyncMock(return_value=True)
            mock_storage.get_metadata = AsyncMock(return_value=MagicMock(size=1024))

            result = await node.run(state)

        assert isinstance(result, ExtractNode)

    @pytest.mark.asyncio
    async def test_preprocess_file_missing(self):
        """File not found returns End with error."""
        state = PreprocessState(
            submission_id="test-123",
            document_paths=["nonexistent.pdf"],
            validation_passed=True,
        )

        node = PreprocessNode()

        with patch(
            "doc_extract.adapters.local_storage.LocalFileSystemAdapter"
        ) as mock_storage_cls:
            mock_storage = mock_storage_cls.return_value
            mock_storage.exists = AsyncMock(return_value=False)

            result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["status"] == "failed"
        assert len(result.data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_preprocess_file_too_large(self):
        """File exceeding size limit returns End with error."""
        state = PreprocessState(
            submission_id="test-123",
            document_paths=["large.pdf"],
            validation_passed=True,
        )

        node = PreprocessNode()

        with patch(
            "doc_extract.adapters.local_storage.LocalFileSystemAdapter"
        ) as mock_storage_cls:
            mock_storage = mock_storage_cls.return_value
            mock_storage.exists = AsyncMock(return_value=True)
            # 100MB file, default limit is 50MB
            mock_storage.get_metadata = AsyncMock(
                return_value=MagicMock(size=100 * 1024 * 1024)
            )

            result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["status"] == "failed"

    @pytest.mark.asyncio
    async def test_preprocess_metadata_error(self):
        """Error getting metadata returns End with error."""
        state = PreprocessState(
            submission_id="test-123",
            document_paths=["error.pdf"],
            validation_passed=True,
        )

        node = PreprocessNode()

        with patch(
            "doc_extract.adapters.local_storage.LocalFileSystemAdapter"
        ) as mock_storage_cls:
            mock_storage = mock_storage_cls.return_value
            mock_storage.exists = AsyncMock(return_value=True)
            mock_storage.get_metadata = AsyncMock(return_value=None)

            result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["status"] == "failed"


# ---------------------------------------------------------------------------
# ValidateNode
# ---------------------------------------------------------------------------


class TestValidateNode:
    """Test validation node."""

    @pytest.mark.asyncio
    async def test_validate_valid_profile(self):
        """Valid profile passes validation."""
        profile = _make_profile()

        state = ExtractState(
            submission_id="test-123",
            raw_extraction=profile.model_dump(),
            extraction_confidence=0.9,
            token_usage={},
            processing_time_seconds=1.5,
        )

        node = ValidateNode()
        result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["status"] == "completed"
        assert result.data["borrower_profile"] is not None

    @pytest.mark.asyncio
    async def test_validate_missing_name(self):
        """Missing/empty name triggers manual review."""
        profile = _make_profile(name=None)

        state = ExtractState(
            submission_id="test-123",
            raw_extraction=profile.model_dump(),
            extraction_confidence=0.9,
            token_usage={},
            processing_time_seconds=1.0,
        )

        node = ValidateNode()
        result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["borrower_profile"] is not None

    @pytest.mark.asyncio
    async def test_validate_low_confidence(self):
        """Low confidence triggers manual review."""
        profile = _make_profile(name="Jane Doe")

        state = ExtractState(
            submission_id="test-123",
            raw_extraction=profile.model_dump(),
            extraction_confidence=0.5,
            token_usage={},
            processing_time_seconds=2.0,
        )

        node = ValidateNode()
        result = await node.run(state)

        assert isinstance(result, End)
        report = result.data["validation_report"]
        assert report["requires_manual_review"] is True

    @pytest.mark.asyncio
    async def test_validate_empty_extraction(self):
        """Empty extraction with low confidence triggers manual review."""
        state = ExtractState(
            submission_id="test-123",
            raw_extraction={},
            extraction_confidence=0.5,
            token_usage={},
            processing_time_seconds=1.0,
        )

        node = ValidateNode()
        result = await node.run(state)

        assert isinstance(result, End)
        report = result.data["validation_report"]
        # Empty extraction reconstructs a profile with all optional fields;
        # low confidence (0.5 < 0.8 threshold) triggers manual review
        assert report["requires_manual_review"] is True

    @pytest.mark.asyncio
    async def test_validate_invalid_extraction_structure(self):
        """Invalid structure triggers profile_structure error."""
        state = ExtractState(
            submission_id="test-123",
            raw_extraction={"invalid": "data"},
            extraction_confidence=0.9,
            token_usage={},
            processing_time_seconds=1.0,
        )

        node = ValidateNode()
        result = await node.run(state)

        assert isinstance(result, End)
        report = result.data["validation_report"]
        assert report["requires_manual_review"] is True


# ---------------------------------------------------------------------------
# ExtractNode
# ---------------------------------------------------------------------------


class TestExtractNode:
    """Test extraction node with mocked LLM."""

    @pytest.mark.asyncio
    async def test_extract_llm_failure(self):
        """LLM failure returns End with error."""
        state = ExtractState(
            submission_id="test-123",
            document_paths=["test.pdf"],
            raw_extraction={},
            extraction_confidence=0.0,
            token_usage={},
            processing_time_seconds=0.0,
        )

        node = ExtractNode()

        with patch("doc_extract.adapters.openai_adapter.OpenAIAdapter") as mock_llm_cls:
            mock_llm = mock_llm_cls.return_value
            mock_llm.extract_structured = AsyncMock(
                side_effect=RuntimeError("LLM unavailable")
            )

            result = await node.run(state)

        assert isinstance(result, End)
        assert result.data["status"] == "failed"
        assert "LLM unavailable" in result.data["errors"][0]["error"]
