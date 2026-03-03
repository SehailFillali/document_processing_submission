"""Tests for cloud adapters with mocked dependencies."""

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doc_extract.ports.storage import StorageMetadata


class TestGCSStorageAdapter:
    """Test GCS adapter with mocked google.cloud.storage."""

    def _create_adapter(self):
        """Create a GCS adapter with mocked client."""
        from doc_extract.adapters.gcs_storage import GCSStorageAdapter

        adapter = GCSStorageAdapter("test-bucket", project_id="test-project")
        # Mock the client and bucket
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        adapter._client = mock_client
        adapter._bucket = mock_bucket
        return adapter, mock_bucket

    @pytest.mark.asyncio
    async def test_gcs_upload(self):
        """Upload stores file and returns metadata."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        content = b"test pdf content"
        result = await adapter.upload(
            BytesIO(content), "docs/test.pdf", content_type="application/pdf"
        )

        assert isinstance(result, StorageMetadata)
        assert result.size == len(content)
        assert "gs://test-bucket/" in result.path

    @pytest.mark.asyncio
    async def test_gcs_download(self):
        """Download retrieves file content."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"file content"
        mock_bucket.blob.return_value = mock_blob

        data = await adapter.download("docs/test.pdf")
        assert data == b"file content"

    @pytest.mark.asyncio
    async def test_gcs_download_gs_scheme(self):
        """Download strips gs:// prefix."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"content"
        mock_bucket.blob.return_value = mock_blob

        await adapter.download("gs://test-bucket/docs/test.pdf")
        mock_bucket.blob.assert_called_with("docs/test.pdf")

    @pytest.mark.asyncio
    async def test_gcs_exists(self):
        """Exists checks blob existence."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket.blob.return_value = mock_blob

        assert await adapter.exists("docs/test.pdf") is True

    @pytest.mark.asyncio
    async def test_gcs_delete_success(self):
        """Delete returns True on success."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        result = await adapter.delete("docs/test.pdf")
        assert result is True

    @pytest.mark.asyncio
    async def test_gcs_delete_failure(self):
        """Delete returns False on failure."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.delete.side_effect = Exception("not found")
        mock_bucket.blob.return_value = mock_blob

        result = await adapter.delete("docs/test.pdf")
        assert result is False

    @pytest.mark.asyncio
    async def test_gcs_get_metadata(self):
        """Get metadata returns StorageMetadata."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.size = 1024
        mock_blob.content_type = "application/pdf"
        mock_blob.updated = datetime.now(UTC)
        mock_bucket.blob.return_value = mock_blob

        meta = await adapter.get_metadata("docs/test.pdf")
        assert meta is not None
        assert meta.size == 1024

    @pytest.mark.asyncio
    async def test_gcs_get_metadata_not_found(self):
        """Get metadata returns None for missing file."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket.blob.return_value = mock_blob

        meta = await adapter.get_metadata("nonexistent.pdf")
        assert meta is None

    @pytest.mark.asyncio
    async def test_gcs_generate_signed_url(self):
        """Generate signed URL calls blob correctly."""
        adapter, mock_bucket = self._create_adapter()
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed-url.com/file"
        mock_bucket.blob.return_value = mock_blob

        url = await adapter.generate_signed_url("docs/test.pdf", 3600)
        assert url == "https://signed-url.com/file"


class TestPubSubAdapter:
    """Test Pub/Sub adapter with mocked google.cloud.pubsub_v1."""

    def _create_adapter(self):
        """Create a Pub/Sub adapter with mocked clients."""
        from doc_extract.adapters.pubsub_adapter import PubSubAdapter

        adapter = PubSubAdapter("test-project")
        mock_publisher = MagicMock()
        mock_subscriber = MagicMock()
        adapter._publisher = mock_publisher
        adapter._subscriber = mock_subscriber
        return adapter, mock_publisher, mock_subscriber

    @pytest.mark.asyncio
    async def test_pubsub_publish(self):
        """Publish sends message and returns ID."""
        adapter, mock_publisher, _ = self._create_adapter()
        mock_publisher.topic_path.return_value = "projects/test/topics/events"
        mock_future = MagicMock()
        mock_future.result.return_value = "msg-123"
        mock_publisher.publish.return_value = mock_future

        msg_id = await adapter.publish("events", {"submission_id": "123"})
        assert msg_id == "msg-123"

    @pytest.mark.asyncio
    async def test_pubsub_acknowledge(self):
        """Acknowledge returns True."""
        adapter, _, _ = self._create_adapter()
        result = await adapter.acknowledge("msg-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_pubsub_reject(self):
        """Reject returns True."""
        adapter, _, _ = self._create_adapter()
        result = await adapter.reject("msg-123", requeue=True, reason="bad data")
        assert result is True

    @pytest.mark.asyncio
    async def test_pubsub_close(self):
        """Close cancels all subscriptions."""
        adapter, _, _ = self._create_adapter()
        mock_future = MagicMock()
        adapter._subscriptions["sub-1"] = mock_future

        await adapter.close()
        mock_future.cancel.assert_called_once()
        assert len(adapter._subscriptions) == 0


class TestOpenAIAdapter:
    """Test OpenAI adapter with mocked client."""

    def test_init(self):
        """Adapter initializes with model name."""
        from doc_extract.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.model_name == "gpt-4o"
        assert adapter.api_key == "test-key"

    def test_get_model_info(self):
        """Model info returns correct data."""
        from doc_extract.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        info = adapter.get_model_info()
        assert info["provider"] == "OpenAI"
        assert "text_extraction" in info["capabilities"]


class TestStorageFactory:
    """Test storage factory."""

    def test_local_backend(self):
        """Local backend returns LocalFileSystemAdapter."""
        with patch("doc_extract.adapters.storage_factory.settings") as mock_settings:
            mock_settings.storage_backend = "local"
            from doc_extract.adapters.local_storage import LocalFileSystemAdapter
            from doc_extract.adapters.storage_factory import get_storage_adapter

            adapter = get_storage_adapter()
            assert isinstance(adapter, LocalFileSystemAdapter)

    def test_minio_backend(self):
        """MinIO backend returns MinIOAdapter."""
        with patch("doc_extract.adapters.storage_factory.settings") as mock_settings:
            mock_settings.storage_backend = "minio"
            mock_settings.minio_endpoint = "localhost:9000"
            mock_settings.minio_access_key = "minioadmin"
            mock_settings.minio_secret_key = "minioadmin"
            mock_settings.minio_secure = False
            mock_settings.minio_bucket_name = "documents"

            with patch(
                "doc_extract.adapters.minio_adapter.MinIOAdapter.__init__",
                return_value=None,
            ):
                from doc_extract.adapters.storage_factory import get_storage_adapter

                adapter = get_storage_adapter()
                from doc_extract.adapters.minio_adapter import MinIOAdapter

                assert isinstance(adapter, MinIOAdapter)

    def test_unknown_backend_raises(self):
        """Unknown backend raises ValueError."""
        with patch("doc_extract.adapters.storage_factory.settings") as mock_settings:
            mock_settings.storage_backend = "unknown"
            from doc_extract.adapters.storage_factory import get_storage_adapter

            with pytest.raises(ValueError, match="Unknown storage backend"):
                get_storage_adapter()


class TestGeminiAdapter:
    """Test Gemini adapter with mocked PydanticAI."""

    def test_get_model_info(self):
        """Model info returns correct data."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from doc_extract.adapters.gemini_adapter import GeminiAdapter

            adapter = GeminiAdapter(api_key="test-key")
            info = adapter.get_model_info()
            assert info["provider"] == "Google Gemini"


class TestResilienceEndpoints:
    """Test resilience API endpoints."""

    def test_circuits_endpoint(self):
        """GET /api/v1/resilience/circuits returns circuit data."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        client = TestClient(app)
        r = client.get("/api/v1/resilience/circuits")
        assert r.status_code == 200
        assert "circuits" in r.json()

    def test_resilience_status(self):
        """GET /api/v1/resilience/status returns status."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        client = TestClient(app)
        r = client.get("/api/v1/resilience/status")
        assert r.status_code == 200
        assert "circuit_breakers" in r.json()

    def test_reset_circuit(self):
        """POST reset endpoint resets circuit."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        client = TestClient(app)
        r = client.post("/api/v1/resilience/circuits/test-circuit/reset")
        assert r.status_code == 200
        assert "reset" in r.json()["message"]


class TestMinIOAdapterUnavailable:
    """Test MinIO adapter when the minio library is not installed."""

    @pytest.mark.asyncio
    async def test_upload_raises_without_minio(self):
        """Upload raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.upload(BytesIO(b"data"), "test/file.pdf")

    @pytest.mark.asyncio
    async def test_download_raises_without_minio(self):
        """Download raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.download("test/file.pdf")

    @pytest.mark.asyncio
    async def test_delete_raises_without_minio(self):
        """Delete raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.delete("test/file.pdf")

    @pytest.mark.asyncio
    async def test_exists_raises_without_minio(self):
        """Exists raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.exists("test/file.pdf")

    @pytest.mark.asyncio
    async def test_signed_url_raises_without_minio(self):
        """Generate signed URL raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.generate_signed_url("test/file.pdf")

    @pytest.mark.asyncio
    async def test_get_metadata_raises_without_minio(self):
        """Get metadata raises ImportError when minio is unavailable."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = False
        with pytest.raises(ImportError, match="MinIO library not installed"):
            await adapter.get_metadata("test/file.pdf")


class TestObservabilityLogfireInit:
    """Test observability init paths."""

    def test_initialize_logfire_disabled(self):
        """initialize_logfire is no-op when disabled."""
        from doc_extract.core.observability import ObservabilityConfig

        config = ObservabilityConfig()
        config.enabled = False
        # Should return without error
        config.initialize_logfire()

    def test_initialize_logfire_when_enabled(self):
        """initialize_logfire calls logfire.configure when enabled and available."""
        from doc_extract.core import observability

        config = observability.ObservabilityConfig()
        config.enabled = True

        mock_logfire = MagicMock()
        original = observability.LOGFIRE_AVAILABLE

        try:
            observability.LOGFIRE_AVAILABLE = True
            with (
                patch.dict("sys.modules", {"logfire": mock_logfire}),
                patch.object(observability, "logfire", mock_logfire, create=True),
            ):
                config.initialize_logfire()
        finally:
            observability.LOGFIRE_AVAILABLE = original

    @pytest.mark.asyncio
    async def test_obs_context_with_logfire_enabled(self):
        """obs_context yields with span when logfire is enabled."""
        from doc_extract.core import observability

        original_available = observability.LOGFIRE_AVAILABLE
        original_enabled = observability.obs_config.enabled

        mock_logfire = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=None)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_logfire.span.return_value = mock_span

        try:
            observability.LOGFIRE_AVAILABLE = True
            observability.obs_config.enabled = True
            with patch.object(observability, "logfire", mock_logfire, create=True):
                async with observability.obs_context("test_op", key="val"):
                    pass
            mock_logfire.span.assert_called_once_with("test_op", key="val")
        finally:
            observability.LOGFIRE_AVAILABLE = original_available
            observability.obs_config.enabled = original_enabled


class TestMinIOAdapterWithMockedClient:
    """Test MinIO adapter operations with a mocked Minio client."""

    def _create_adapter(self):
        """Create a MinIO adapter with mocked client."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter._minio_available = True
        adapter._S3Error = Exception
        adapter.client = MagicMock()
        adapter.endpoint = "localhost:9000"
        adapter.bucket_name = "documents"
        adapter.access_key = "minioadmin"
        adapter.secret_key = "minioadmin"
        adapter.secure = False
        return adapter

    @pytest.mark.asyncio
    async def test_upload_success(self):
        """Upload stores file and returns metadata."""
        adapter = self._create_adapter()
        content = b"test pdf content"

        result = await adapter.upload(
            BytesIO(content), "test/file.pdf", content_type="application/pdf"
        )

        assert isinstance(result, StorageMetadata)
        assert result.size == len(content)
        assert result.checksum is not None
        adapter.client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_success(self):
        """Download returns file content."""
        adapter = self._create_adapter()
        mock_response = MagicMock()
        mock_response.read.return_value = b"file content"
        adapter.client.get_object.return_value = mock_response

        data = await adapter.download("test/file.pdf")
        assert data == b"file content"
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_not_found(self):
        """Download raises FileNotFoundError on S3Error."""
        adapter = self._create_adapter()
        adapter.client.get_object.side_effect = Exception("NoSuchKey")

        with pytest.raises(FileNotFoundError):
            await adapter.download("nonexistent.pdf")

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Delete returns True on success."""
        adapter = self._create_adapter()
        result = await adapter.delete("test/file.pdf")
        assert result is True
        adapter.client.remove_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_failure(self):
        """Delete returns False on S3Error."""
        adapter = self._create_adapter()
        adapter.client.remove_object.side_effect = Exception("err")
        result = await adapter.delete("test/file.pdf")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Exists returns True when object found."""
        adapter = self._create_adapter()
        result = await adapter.exists("test/file.pdf")
        assert result is True
        adapter.client.stat_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Exists returns False on S3Error."""
        adapter = self._create_adapter()
        adapter.client.stat_object.side_effect = Exception("NotFound")
        result = await adapter.exists("nonexistent.pdf")
        assert result is False

    @pytest.mark.asyncio
    async def test_generate_signed_url(self):
        """Signed URL returns presigned URL string."""
        adapter = self._create_adapter()
        adapter.client.presigned_get_object.return_value = "https://signed.url/file"
        url = await adapter.generate_signed_url("test/file.pdf", 3600)
        assert url == "https://signed.url/file"

    @pytest.mark.asyncio
    async def test_get_metadata_success(self):
        """Get metadata returns StorageMetadata."""
        adapter = self._create_adapter()
        mock_stat = MagicMock()
        mock_stat.size = 2048
        mock_stat.content_type = "application/pdf"
        mock_stat.last_modified = datetime.now(UTC)
        mock_stat.etag = '"abc123"'
        adapter.client.stat_object.return_value = mock_stat

        meta = await adapter.get_metadata("test/file.pdf")
        assert meta is not None
        assert meta.size == 2048
        assert meta.checksum == "abc123"

    @pytest.mark.asyncio
    async def test_get_metadata_not_found(self):
        """Get metadata returns None on S3Error."""
        adapter = self._create_adapter()
        adapter.client.stat_object.side_effect = Exception("NotFound")
        meta = await adapter.get_metadata("nonexistent.pdf")
        assert meta is None

    def test_ensure_bucket_exists_creates(self):
        """Ensure bucket creates new bucket if missing."""
        adapter = self._create_adapter()
        adapter.client.bucket_exists.return_value = False
        adapter._ensure_bucket_exists()
        adapter.client.make_bucket.assert_called_once_with("documents")

    def test_ensure_bucket_exists_already(self):
        """Ensure bucket skips creation if exists."""
        adapter = self._create_adapter()
        adapter.client.bucket_exists.return_value = True
        adapter._ensure_bucket_exists()
        adapter.client.make_bucket.assert_not_called()

    def test_ensure_bucket_exists_error(self):
        """Ensure bucket handles errors gracefully."""
        adapter = self._create_adapter()
        adapter.client.bucket_exists.side_effect = Exception("connection failed")
        # Should not raise
        adapter._ensure_bucket_exists()


class TestOpenAIAdapterExtraction:
    """Test OpenAI adapter extraction with mocked AsyncOpenAI client."""

    @pytest.mark.asyncio
    async def test_extract_structured_success(self):
        """Successful extraction returns ExtractionResponse."""
        from pydantic import BaseModel

        from doc_extract.adapters.openai_adapter import OpenAIAdapter
        from doc_extract.ports.llm import ExtractionRequest, ExtractionResponse

        class TestSchema(BaseModel):
            name: str
            amount: float

        adapter = OpenAIAdapter(api_key="test-key")
        request = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
        )

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150

        mock_message = MagicMock()
        mock_message.content = '{"name": "John", "amount": 5000.0}'

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter.extract_structured(request)

        assert isinstance(result, ExtractionResponse)
        assert result.extracted_data.name == "John"
        assert result.token_usage["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_extract_structured_failure(self):
        """Extraction failure raises LLMError."""
        from pydantic import BaseModel

        from doc_extract.adapters.openai_adapter import OpenAIAdapter
        from doc_extract.ports.llm import ExtractionRequest, LLMError

        class TestSchema(BaseModel):
            name: str

        adapter = OpenAIAdapter(api_key="test-key")
        request = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API error")
        )

        with (
            patch(
                "openai.AsyncOpenAI",
                return_value=mock_client,
            ),
            pytest.raises(LLMError, match="Extraction failed"),
        ):
            await adapter.extract_structured(request)

    @pytest.mark.asyncio
    async def test_validate_connection_success(self):
        """Validate connection returns True on success."""
        from doc_extract.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")

        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(return_value=[])

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter.validate_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self):
        """Validate connection returns False on error."""
        from doc_extract.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")

        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(side_effect=RuntimeError("no auth"))

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await adapter.validate_connection()
        assert result is False


class TestGeminiAdapterExtraction:
    """Test Gemini adapter extraction with mocked PydanticAI agent."""

    @pytest.mark.asyncio
    async def test_extract_structured_success(self):
        """Successful extraction returns ExtractionResponse."""
        from pydantic import BaseModel

        from doc_extract.adapters.gemini_adapter import GeminiAdapter
        from doc_extract.ports.llm import ExtractionRequest, ExtractionResponse

        class TestSchema(BaseModel):
            name: str

        mock_result = MagicMock()
        mock_result.data = TestSchema(name="Jane Doe")
        mock_result.input_tokens = 200
        mock_result.output_tokens = 100

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            adapter = GeminiAdapter(api_key="test-key")

        request = ExtractionRequest(
            document_url="file://test.pdf",
            document_type="loan_application",
            output_schema=TestSchema,
        )

        with patch("pydantic_ai.Agent", return_value=mock_agent):
            result = await adapter.extract_structured(request)

        assert isinstance(result, ExtractionResponse)
        assert result.extracted_data.name == "Jane Doe"
        assert result.model_name == "gemini-1.5-flash"

    @pytest.mark.asyncio
    async def test_validate_connection(self):
        """Validate connection attempts agent creation and handles result."""
        from doc_extract.adapters.gemini_adapter import GeminiAdapter

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            adapter = GeminiAdapter(api_key="test-key")

        # Agent() constructor is awaited in source code, which raises
        # TypeError for non-coroutine returns — caught by except → False.
        # To get True, we'd need a real Agent. This tests the error path.
        with patch("pydantic_ai.Agent"):
            result = await adapter.validate_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_connection_success(self):
        """Validate connection returns True when Agent is awaitable."""
        from doc_extract.adapters.gemini_adapter import GeminiAdapter

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            adapter = GeminiAdapter(api_key="test-key")

        # Agent() is awaited in source, so mock must be AsyncMock
        # so that `await AsyncMock(...)` works
        with patch("pydantic_ai.Agent", new=AsyncMock()):
            result = await adapter.validate_connection()
        assert result is True

    def test_cost_tracking_functions(self):
        """Cost tracking functions work correctly."""
        from doc_extract.adapters.gemini_adapter import (
            _cost_tracker,
            get_submission_cost,
            get_total_system_cost,
            track_extraction_cost,
        )

        _cost_tracker.clear()

        track_extraction_cost("sub-1", 0.05)
        track_extraction_cost("sub-1", 0.03)
        track_extraction_cost("sub-2", 0.10)

        assert get_submission_cost("sub-1") == pytest.approx(0.08)
        assert get_submission_cost("sub-2") == pytest.approx(0.10)
        assert get_submission_cost("nonexistent") == 0.0
        assert get_total_system_cost() == pytest.approx(0.18)

        _cost_tracker.clear()


class TestPubSubAdapterSubscribe:
    """Test Pub/Sub subscribe and DLQ paths."""

    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Subscribe creates subscription and starts listening."""
        from doc_extract.adapters.pubsub_adapter import PubSubAdapter

        adapter = PubSubAdapter("test-project")
        mock_publisher = MagicMock()
        mock_subscriber = MagicMock()
        adapter._publisher = mock_publisher
        adapter._subscriber = mock_subscriber

        mock_publisher.topic_path.return_value = "projects/test/topics/events"
        mock_subscriber.subscription_path.return_value = (
            "projects/test/subscriptions/events-sub"
        )
        mock_subscriber.subscribe.return_value = MagicMock()  # future

        async def handler(msg):
            pass

        sub = await adapter.subscribe("events", handler)
        assert sub.subscription_id is not None
        assert len(adapter._subscriptions) == 1

    @pytest.mark.asyncio
    async def test_publish_to_dlq(self):
        """Publish to DLQ sends message to DLQ topic."""
        from doc_extract.adapters.pubsub_adapter import PubSubAdapter
        from doc_extract.ports.queue import QueueMessage

        adapter = PubSubAdapter("test-project")
        mock_publisher = MagicMock()
        adapter._publisher = mock_publisher

        mock_publisher.topic_path.return_value = "projects/test/topics/events-dlq"
        mock_future = MagicMock()
        mock_future.result.return_value = "dlq-msg-123"
        mock_publisher.publish.return_value = mock_future

        msg = QueueMessage(
            message_id="orig-123",
            body={"topic": "events", "data": "bad"},
            timestamp=datetime.now(UTC),
        )

        result = await adapter.publish_to_dlq(msg, reason="parse error")
        assert result == "dlq-msg-123"


class TestBlobEndpointsHappyPath:
    """Test blob endpoints with mocked storage."""

    def _mock_db(self):
        """Create a mock SQLiteAdapter for blob tests."""
        mock_db = MagicMock()
        mock_db.init_tables = AsyncMock()
        mock_db.create = AsyncMock(return_value="test-id")
        mock_db.read = AsyncMock(return_value=None)
        mock_db.update = AsyncMock(return_value=True)
        mock_db.query = AsyncMock(
            return_value=MagicMock(items=[], total_count=0, page=1, page_size=20)
        )
        return mock_db

    def test_process_from_blob_success(self):
        """Happy path: blob exists, downloads, processes."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_storage = MagicMock()
        mock_storage.exists = AsyncMock(return_value=True)
        mock_storage.get_metadata = AsyncMock(
            return_value=StorageMetadata(
                path="minio://docs/test.pdf",
                size=1024,
                content_type="application/pdf",
                created_at=datetime.now(UTC),
            )
        )
        mock_storage.download = AsyncMock(return_value=b"fake pdf bytes")

        with (
            patch("doc_extract.api.main.db", self._mock_db()),
            patch(
                "doc_extract.api.blob_endpoints.get_storage_adapter",
                return_value=mock_storage,
            ),
            patch("doc_extract.api.blob_endpoints.ProcessingService") as mock_proc_cls,
        ):
            mock_proc = mock_proc_cls.return_value
            mock_proc.process_submission = AsyncMock(
                return_value={"status": "success", "data": {"name": "Test"}}
            )

            client = TestClient(app)
            r = client.post(
                "/api/v1/documents/process_uploaded_blob",
                json={"uri": "minio://docs/test.pdf"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["submission_id"] is not None
        assert "processed successfully" in data["message"]

    def test_process_from_blob_no_metadata(self):
        """Returns 404 when metadata cannot be retrieved."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_storage = MagicMock()
        mock_storage.exists = AsyncMock(return_value=True)
        mock_storage.get_metadata = AsyncMock(return_value=None)

        with (
            patch("doc_extract.api.main.db", self._mock_db()),
            patch(
                "doc_extract.api.blob_endpoints.get_storage_adapter",
                return_value=mock_storage,
            ),
        ):
            client = TestClient(app)
            r = client.post(
                "/api/v1/documents/process_uploaded_blob",
                json={"uri": "minio://docs/test.pdf"},
            )

        assert r.status_code == 404
        assert "metadata" in r.json()["detail"].lower()

    def test_process_from_blob_processing_failure(self):
        """Processing failure sets submission to failed status."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_storage = MagicMock()
        mock_storage.exists = AsyncMock(return_value=True)
        mock_storage.get_metadata = AsyncMock(
            return_value=StorageMetadata(
                path="minio://docs/test.pdf",
                size=512,
                content_type="application/pdf",
                created_at=datetime.now(UTC),
            )
        )
        mock_storage.download = AsyncMock(return_value=b"pdf bytes")

        with (
            patch("doc_extract.api.main.db", self._mock_db()),
            patch(
                "doc_extract.api.blob_endpoints.get_storage_adapter",
                return_value=mock_storage,
            ),
            patch("doc_extract.api.blob_endpoints.ProcessingService") as mock_proc_cls,
        ):
            mock_proc = mock_proc_cls.return_value
            mock_proc.process_submission = AsyncMock(
                return_value={"status": "error", "error": "LLM unavailable"}
            )

            client = TestClient(app)
            r = client.post(
                "/api/v1/documents/process_uploaded_blob",
                json={"uri": "minio://docs/test.pdf"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "failed"

    def test_blob_health_with_client(self):
        """Blob health reports healthy when client is connected."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.list_buckets.return_value = []

        with (
            patch(
                "doc_extract.api.blob_endpoints.get_storage_adapter",
                return_value=mock_storage,
            ),
            patch("doc_extract.api.blob_endpoints.settings") as mock_settings,
        ):
            mock_settings.storage_backend = "minio"
            mock_settings.minio_endpoint = "localhost:9000"
            mock_settings.minio_bucket_name = "documents"

            client = TestClient(app)
            r = client.get("/api/v1/blob/health")

        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_blob_health_unhealthy(self):
        """Blob health reports unhealthy on error."""
        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        mock_storage = MagicMock()
        mock_storage.client = MagicMock()
        mock_storage.client.list_buckets.side_effect = ConnectionError("refused")

        with (
            patch(
                "doc_extract.api.blob_endpoints.get_storage_adapter",
                return_value=mock_storage,
            ),
            patch("doc_extract.api.blob_endpoints.settings") as mock_settings,
        ):
            mock_settings.storage_backend = "minio"

            client = TestClient(app)
            r = client.get("/api/v1/blob/health")

        assert r.status_code == 200
        assert r.json()["status"] == "unhealthy"
