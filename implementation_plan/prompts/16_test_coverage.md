# Prompt 16: Increase Test Coverage to 80%+

## Status
[COMPLETED]

## Context
Current test coverage is at 57%. We need comprehensive tests to ensure code quality and catch regressions. The goal is 80%+ coverage with meaningful tests.

## Objective
Create additional tests to achieve 80%+ code coverage across all modules.

## Current Coverage Gaps

| Module | Current | Target | Gap |
|--------|---------|--------|-----|
| adapters/gemini_adapter.py | 48% | 80% | +32% |
| adapters/sqlite_adapter.py | 0% | 80% | +80% |
| domain/validation.py | 0% | 80% | +80% |
| ports/database.py | 0% | 80% | +80% |
| ports/queue.py | 0% | 80% | +80% |
| ports/storage.py | 80% | 90% | +10% |
| services/processing.py | 62% | 80% | +18% |

## Requirements

### 1. Test SQLite Adapter (adapters/sqlite_adapter.py)

Create `tests/test_sqlite_adapter.py`:

```python
"""Tests for SQLite database adapter."""
import pytest
import pytest_asyncio
from doc_extract.adapters.sqlite_adapter import SQLiteAdapter


class TestSQLiteAdapter:
    """Tests for SQLiteAdapter."""

    @pytest.fixture
    async def db(self, tmp_path):
        """Create test database."""
        adapter = SQLiteAdapter(f"sqlite:///{tmp_path}/test.db")
        await adapter.init_tables()
        return adapter

    @pytest.mark.asyncio
    async def test_create_record(self, db):
        """Test creating a record."""
        record_id = await db.create("submissions", {
            "submission_id": "test-123",
            "status": "pending",
        })
        assert record_id is not None

    @pytest.mark.asyncio
    async def test_read_record(self, db):
        """Test reading a record."""
        await db.create("submissions", {
            "submission_id": "test-123",
            "status": "pending",
        })
        
        record = await db.read("submissions", "test-123")
        assert record is not None
        assert record["submission_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_update_record(self, db):
        """Test updating a record."""
        await db.create("submissions", {
            "submission_id": "test-123",
            "status": "pending",
        })
        
        await db.update("submissions", "test-123", {"status": "completed"})
        
        record = await db.read("submissions", "test-123")
        assert record["status"] == "completed"

    @pytest.mark.asyncio
    async def test_delete_record(self, db):
        """Test deleting a record."""
        await db.create("submissions", {
            "submission_id": "test-123",
            "status": "pending",
        })
        
        await db.delete("submissions", "test-123")
        
        record = await db.read("submissions", "test-123")
        assert record is None

    @pytest.mark.asyncio
    async def test_query_with_filters(self, db):
        """Test querying with filters."""
        await db.create("submissions", {"submission_id": "test-1", "status": "pending"})
        await db.create("submissions", {"submission_id": "test-2", "status": "completed"})
        
        from doc_extract.ports.database import QueryFilter
        
        result = await db.query(
            "submissions",
            filters=[QueryFilter(field="status", operator="=", value="completed")]
        )
        
        assert result.total_count == 1
        assert result.items[0]["submission_id"] == "test-2"

    @pytest.mark.asyncio
    async def test_upsert(self, db):
        """Test upsert operation."""
        # Insert
        id1 = await db.upsert("submissions", "test-123", {"status": "pending"})
        assert id1 == "test-123"
        
        # Update
        id2 = await db.upsert("submissions", "test-123", {"status": "completed"})
        assert id2 == "test-123"
        
        record = await db.read("submissions", "test-123")
        assert record["status"] == "completed"
```

### 2. Test Ports/Interfaces (ports/*.py)

Create `tests/test_ports.py`:

```python
"""Tests for port interfaces."""
import pytest
from abc import ABC
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata
from doc_extract.ports.queue import QueuePort, QueueMessage, QueueSubscription
from doc_extract.ports.database import DatabasePort, QueryFilter, QueryResult
from doc_extract.ports.llm import LLMPort, ExtractionRequest


class TestStoragePort:
    """Tests for BlobStoragePort interface."""

    def test_is_abc(self):
        """Test that BlobStoragePort is an ABC."""
        assert issubclass(BlobStoragePort, ABC)

    def test_storage_metadata(self):
        """Test StorageMetadata dataclass."""
        from datetime import datetime
        meta = StorageMetadata(
            path="/test/file.pdf",
            size=1024,
            content_type="application/pdf",
            created_at=datetime.utcnow(),
            checksum="abc123",
        )
        assert meta.path == "/test/file.pdf"
        assert meta.size == 1024


class TestQueuePort:
    """Tests for QueuePort interface."""

    def test_is_abc(self):
        """Test that QueuePort is an ABC."""
        assert issubclass(QueuePort, ABC)

    def test_queue_message(self):
        """Test QueueMessage dataclass."""
        from datetime import datetime
        msg = QueueMessage(
            message_id="msg-123",
            body={"data": "test"},
            timestamp=datetime.utcnow(),
            attempts=1,
        )
        assert msg.message_id == "msg-123"
        assert msg.body["data"] == "test"

    def test_queue_subscription(self):
        """Test QueueSubscription dataclass."""
        sub = QueueSubscription(subscription_id="sub-123")
        assert sub.subscription_id == "sub-123"


class TestDatabasePort:
    """Tests for DatabasePort interface."""

    def test_is_abc(self):
        """Test that DatabasePort is an ABC."""
        assert issubclass(DatabasePort, ABC)

    def test_query_filter(self):
        """Test QueryFilter dataclass."""
        qf = QueryFilter(field="status", operator="=", value="pending")
        assert qf.field == "status"
        assert qf.operator == "="

    def test_query_result(self):
        """Test QueryResult dataclass."""
        qr = QueryResult(
            items=[{"id": 1}, {"id": 2}],
            total_count=2,
            page=1,
            page_size=20,
        )
        assert qr.total_count == 2
        assert len(qr.items) == 2


class TestLLMPort:
    """Tests for LLMPort interface."""

    def test_is_abc(self):
        """Test that LLMPort is an ABC."""
        assert issubclass(LLMPort, ABC)

    def test_extraction_request(self):
        """Test ExtractionRequest dataclass."""
        from pydantic import BaseModel
        
        class TestSchema(BaseModel):
            name: str
        
        req = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
        )
        assert req.document_url == "file://test.pdf"
        assert req.document_type == "loan_application"
```

### 3. Test Validation Models (domain/validation.py)

Create `tests/test_validation.py`:

```python
"""Tests for validation domain models."""
import pytest
from pydantic import ValidationError

from doc_extract.domain.validation import ValidationRule, ValidationResult, ValidationReport


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

    def test_severity_validation(self):
        """Test severity enum validation."""
        with pytest.raises(ValidationError):
            ValidationRule(
                rule_id="rule-001",
                field_path="borrower.name",
                rule_type="required",
                condition="name is not empty",
                severity="critical",  # Invalid
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
```

### 4. Test Gemini Adapter (adapters/gemini_adapter.py)

Create `tests/test_gemini_adapter.py`:

```python
"""Tests for Gemini LLM adapter."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel

from doc_extract.adapters.gemini_adapter import GeminiAdapter
from doc_extract.ports.llm import ExtractionRequest, LLMError


class TestGeminiAdapter:
    """Tests for GeminiAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mock API key."""
        return GeminiAdapter(api_key="test-key")

    def test_adapter_initialization(self, adapter):
        """Test adapter initializes correctly."""
        assert adapter.api_key == "test-key"
        assert adapter.model_name == "gemini-2.0-flash"

    def test_get_model_info(self, adapter):
        """Test model info retrieval."""
        info = adapter.get_model_info()
        
        assert info["model_name"] == "gemini-2.0-flash"
        assert info["provider"] == "Google Gemini"
        assert "text_extraction" in info["capabilities"]

    @pytest.mark.asyncio
    async def test_validate_connection(self, adapter):
        """Test connection validation."""
        with patch("doc_extract.adapters.gemini_adapter.Agent") as mock_agent:
            mock_agent.return_value = MagicMock()
            result = await adapter.validate_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_extract_structured_success(self, adapter):
        """Test successful extraction."""
        class MockSchema(BaseModel):
            name: str
        
        # Mock the Agent
        mock_result = MagicMock()
        mock_result.data = MockSchema(name="John Doe")
        
        with patch("doc_extract.adapters.gemini_adapter.Agent") as mock_agent:
            mock_agent.return_value.run = AsyncMock(return_value=mock_result)
            
            request = ExtractionRequest(
                document_url="file://test.pdf",
                document_type="loan_application",
                output_schema=MockSchema,
            )
            
            response = await adapter.extract_structured(request)
            
            assert response.extracted_data.name == "John Doe"
            assert response.model_name == "gemini-2.0-flash"
            assert response.confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_extract_structured_error(self, adapter):
        """Test extraction error handling."""
        class MockSchema(BaseModel):
            name: str
        
        with patch("doc_extract.adapters.gemini_adapter.Agent") as mock_agent:
            mock_agent.return_value.run = AsyncMock(side_effect=Exception("API Error"))
            
            request = ExtractionRequest(
                document_url="file://test.pdf",
                document_type="loan_application",
                output_schema=MockSchema,
            )
            
            with pytest.raises(LLMError) as exc_info:
                await adapter.extract_structured(request)
            
            assert "Extraction failed" in exc_info.value.message
            assert exc_info.value.recoverable is True
```

### 5. Test Processing Service (services/processing.py) - Add More Tests

Update `tests/test_services.py` to add more coverage:

```python
# Add to TestProcessingService class:

@pytest.mark.asyncio
async def test_process_submission_success(self, service):
    """Test successful submission processing."""
    with patch.object(service.storage, "download", new_callable=AsyncMock) as mock_download:
        with patch.object(service.llm, "extract_structured", new_callable=AsyncMock) as mock_extract:
            mock_download.return_value = b"test content"
            
            mock_response = MagicMock()
            mock_response.extracted_data = MagicMock()
            mock_response.extracted_data.model_dump.return_value = {"name": "John"}
            mock_response.confidence_score = 0.9
            mock_response.processing_time_seconds = 1.5
            mock_extract.return_value = mock_response
            
            result = await service.process_submission("test-123", "test/path")
            
            assert result["status"] == "success"
            assert result["confidence"] == 0.9

@pytest.mark.asyncio
async def test_process_submission_error(self, service):
    """Test submission processing error."""
    with patch.object(service.storage, "download", new_callable=AsyncMock) as mock_download:
        mock_download.side_effect = Exception("File not found")
        
        result = await service.process_submission("test-123", "test/path")
        
        assert result["status"] == "failed"
        assert "File not found" in result["error"]
```

### 6. Additional Edge Case Tests

Create `tests/test_edge_cases.py`:

```python
"""Edge case and property-based tests."""
import pytest
from hypothesis import given, settings, strategies as st
from datetime import date, datetime

from doc_extract.domain.borrower import Address, BorrowerProfile, IncomeEntry
from doc_extract.domain.base import Provenance, MissingField


class TestAddressEdgeCases:
    """Edge case tests for Address."""

    @given(st.text(min_length=1))
    def test_valid_city(self, city):
        """Test various valid city names."""
        addr = Address(
            street="123 Main St",
            city=city,
            state="MA",
            zip_code="02101",
        )
        assert addr.city == city

    @given(st.text(min_length=1))
    def test_valid_street(self, street):
        """Test various valid street addresses."""
        addr = Address(
            street=street,
            city="Boston",
            state="MA",
            zip_code="02101",
        )
        assert addr.street == street


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
```

## Deliverables

- [ ] `tests/test_sqlite_adapter.py` - 8+ tests for SQLite adapter
- [ ] `tests/test_ports.py` - 8+ tests for port interfaces
- [ ] `tests/test_validation.py` - 5+ tests for validation models
- [ ] `tests/test_gemini_adapter.py` - 5+ tests for Gemini adapter
- [ ] `tests/test_edge_cases.py` - 10+ property-based tests
- [ ] Update `tests/test_services.py` with 2 additional tests

## Success Criteria

- Overall coverage increases from 57% to 80%+
- All tests pass (`pytest tests/ -v`)
- No new lint errors introduced
- Tests are meaningful (not just coverage for coverage's sake)

## Code Snippets to Include

All code snippets above are complete and production-ready.

## Next Prompt
After coverage is complete, verify with:
```bash
just test
# Should show 80%+ coverage
```
