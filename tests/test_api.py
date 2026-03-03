"""Tests for API endpoints."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from doc_extract.api.main import app


@pytest.fixture(autouse=True)
def _mock_db():
    """Mock SQLiteAdapter so tests don't need a real database."""
    mock = MagicMock()
    mock.init_tables = AsyncMock()
    mock.create = AsyncMock(return_value="test-id")
    mock.read = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=True)
    mock.query = AsyncMock(
        return_value=MagicMock(items=[], total_count=0, page=1, page_size=20)
    )
    with patch("doc_extract.api.main.db", mock):
        yield mock


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestUploadEndpoint:
    """Tests for document upload endpoint."""

    def test_upload_requires_file(self, client):
        """Test upload requires a file."""
        response = client.post("/api/v1/documents/upload")
        assert response.status_code == 422

    @patch("doc_extract.api.main.storage")
    def test_upload_success(self, mock_storage, _mock_db, client):
        """Test successful file upload."""
        mock_storage.upload = AsyncMock(
            return_value=MagicMock(
                path="/test/file.pdf",
                size=100,
                content_type="application/pdf",
            )
        )

        # Mock ProcessingService so upload doesn't actually call LLM
        with patch("doc_extract.api.main.ProcessingService", create=True) as mock_ps:
            mock_proc = MagicMock()
            mock_proc.process_submission = AsyncMock(
                return_value={"status": "success", "data": {"name": "Test"}}
            )
            mock_ps.return_value = mock_proc

            files = {"file": ("test.pdf", BytesIO(b"test content"), "application/pdf")}
            response = client.post(
                "/api/v1/documents/upload",
                files=files,
            )

        assert response.status_code == 200
        data = response.json()
        assert "submission_id" in data
        assert data["status"] in ("completed", "processing", "failed")


class TestSubmissionsEndpoint:
    """Tests for submissions endpoints."""

    def test_get_submission_not_found(self, client):
        """Test getting non-existent submission."""
        response = client.get("/api/v1/submissions/nonexistent-id")
        assert response.status_code == 404

    def test_list_submissions(self, client):
        """Test listing submissions."""
        response = client.get("/api/v1/submissions")
        assert response.status_code == 200
        data = response.json()
        assert "submissions" in data
