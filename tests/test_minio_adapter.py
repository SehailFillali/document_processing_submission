"""Tests for MinIO adapter."""

import pytest


class TestMinIOAdapter:
    """Tests for MinIOAdapter."""

    def test_parse_uri_minio(self):
        """Test URI parsing for minio:// scheme."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)

        bucket, obj = adapter._parse_uri("minio://mybucket/document.pdf")
        assert bucket == "mybucket"
        assert obj == "document.pdf"

    def test_parse_uri_s3(self):
        """Test URI parsing for s3:// scheme."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)

        bucket, obj = adapter._parse_uri("s3://mybucket/folder/document.pdf")
        assert bucket == "mybucket"
        assert obj == "folder/document.pdf"

    def test_parse_uri_gs(self):
        """Test URI parsing for gs:// scheme."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)

        bucket, obj = adapter._parse_uri("gs://mybucket/document.pdf")
        assert bucket == "mybucket"
        assert obj == "document.pdf"

    def test_parse_uri_plain(self):
        """Test URI parsing for plain paths."""
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        adapter = MinIOAdapter.__new__(MinIOAdapter)
        adapter.bucket_name = "default-bucket"

        bucket, obj = adapter._parse_uri("path/to/document.pdf")
        assert bucket == "default-bucket"
        assert obj == "path/to/document.pdf"


class TestBlobEndpoint:
    """Tests for blob storage endpoints."""

    def _mock_db(self):
        """Create a mock SQLiteAdapter."""
        from unittest.mock import AsyncMock, MagicMock

        mock = MagicMock()
        mock.init_tables = AsyncMock()
        mock.create = AsyncMock(return_value="test-id")
        mock.read = AsyncMock(return_value=None)
        mock.update = AsyncMock(return_value=True)
        mock.query = AsyncMock(
            return_value=MagicMock(items=[], total_count=0, page=1, page_size=20)
        )
        return mock

    @pytest.mark.asyncio
    async def test_process_from_blob_invalid_uri(self):
        """Test blob endpoint with invalid URI."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        with patch("doc_extract.api.main.db", self._mock_db()):
            client = TestClient(app)

            response = client.post(
                "/api/v1/documents/process_uploaded_blob",
                json={"uri": "not-a-valid-uri", "document_type": "loan_application"},
            )

        assert response.status_code == 400

    def test_blob_health_endpoint(self):
        """Test blob storage health check."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from doc_extract.api.main import app

        with patch("doc_extract.api.main.db", self._mock_db()):
            client = TestClient(app)

            response = client.get("/api/v1/blob/health")

        assert response.status_code == 200
