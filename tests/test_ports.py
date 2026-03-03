"""Tests for port interfaces."""

from abc import ABC
from datetime import UTC, datetime

from pydantic import BaseModel

from doc_extract.ports.database import DatabasePort, QueryFilter, QueryResult
from doc_extract.ports.llm import ExtractionRequest, LLMPort
from doc_extract.ports.queue import QueueMessage, QueuePort, QueueSubscription
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata


class TestStoragePort:
    """Tests for BlobStoragePort interface."""

    def test_is_abc(self):
        """Test that BlobStoragePort is an ABC."""
        assert issubclass(BlobStoragePort, ABC)

    def test_storage_metadata(self):
        """Test StorageMetadata dataclass."""
        meta = StorageMetadata(
            path="/test/file.pdf",
            size=1024,
            content_type="application/pdf",
            created_at=datetime.now(UTC),
            checksum="abc123",
        )
        assert meta.path == "/test/file.pdf"
        assert meta.size == 1024

    def test_storage_metadata_without_checksum(self):
        """Test StorageMetadata without optional checksum."""
        meta = StorageMetadata(
            path="/test/file.pdf",
            size=1024,
            content_type="application/pdf",
            created_at=datetime.now(UTC),
        )
        assert meta.checksum is None


class TestQueuePort:
    """Tests for QueuePort interface."""

    def test_is_abc(self):
        """Test that QueuePort is an ABC."""
        assert issubclass(QueuePort, ABC)

    def test_queue_message(self):
        """Test QueueMessage dataclass."""
        msg = QueueMessage(
            message_id="msg-123",
            body={"data": "test"},
            timestamp=datetime.now(UTC),
            attempts=1,
        )
        assert msg.message_id == "msg-123"
        assert msg.body["data"] == "test"

    def test_queue_message_with_metadata(self):
        """Test QueueMessage with metadata."""
        msg = QueueMessage(
            message_id="msg-123",
            body={"data": "test"},
            timestamp=datetime.now(UTC),
            attempts=1,
            metadata={"retry": True},
        )
        assert msg.metadata is not None
        assert msg.metadata["retry"] is True

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
        assert qf.value == "pending"

    def test_query_filter_operators(self):
        """Test different query filter operators."""
        operators = ["=", "!=", ">", "<", ">=", "<=", "in", "contains"]
        for op in operators:
            qf = QueryFilter(field="id", operator=op, value="test")
            assert qf.operator == op

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
        assert qr.page == 1
        assert qr.page_size == 20


class TestLLMPort:
    """Tests for LLMPort interface."""

    def test_is_abc(self):
        """Test that LLMPort is an ABC."""
        assert issubclass(LLMPort, ABC)

    def test_extraction_request(self):
        """Test ExtractionRequest dataclass."""

        class TestSchema(BaseModel):
            name: str

        req = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
        )
        assert req.document_url == "file://test.pdf"
        assert req.document_type == "loan_application"

    def test_extraction_request_with_prompt(self):
        """Test ExtractionRequest with custom prompt."""

        class TestSchema(BaseModel):
            name: str

        req = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
            system_prompt="Extract borrower info",
        )
        assert req.system_prompt == "Extract borrower info"

    def test_extraction_request_with_validation_rules(self):
        """Test ExtractionRequest with validation rules."""

        class TestSchema(BaseModel):
            name: str

        rules = [{"field": "name", "rule": "required"}]
        req = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
            validation_rules=rules,
        )
        assert req.validation_rules == rules
