"""Tests for adapters."""

from io import BytesIO

import pytest

from doc_extract.adapters.local_storage import LocalFileSystemAdapter


class TestLocalFileSystemAdapter:
    """Tests for LocalFileSystemAdapter."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create storage adapter with temp directory."""
        return LocalFileSystemAdapter(base_path=str(tmp_path))

    @pytest.mark.asyncio
    async def test_upload_file(self, storage):
        """Test file upload."""
        content = b"Test file content"
        file_data = BytesIO(content)

        metadata = await storage.upload(
            file_data,
            "test/document.pdf",
            content_type="application/pdf",
        )

        assert metadata.size == len(content)
        assert metadata.checksum is not None

    @pytest.mark.asyncio
    async def test_download_file(self, storage):
        """Test file download."""
        content = b"Test file content"
        await storage.upload(
            BytesIO(content),
            "test/document.pdf",
        )

        downloaded = await storage.download("test/document.pdf")
        assert downloaded == content

    @pytest.mark.asyncio
    async def test_exists(self, storage):
        """Test file existence check."""
        assert not await storage.exists("test/document.pdf")

        await storage.upload(
            BytesIO(b"content"),
            "test/document.pdf",
        )

        assert await storage.exists("test/document.pdf")

    @pytest.mark.asyncio
    async def test_delete_file(self, storage):
        """Test file deletion."""
        await storage.upload(
            BytesIO(b"content"),
            "test/document.pdf",
        )

        assert await storage.exists("test/document.pdf")
        await storage.delete("test/document.pdf")
        assert not await storage.exists("test/document.pdf")

    @pytest.mark.asyncio
    async def test_generate_signed_url(self, storage):
        """Test signed URL generation."""
        url = await storage.generate_signed_url("test/document.pdf")
        assert url.startswith("file://")

    @pytest.mark.asyncio
    async def test_get_metadata(self, storage):
        """Test metadata retrieval."""
        content = b"Test content"
        await storage.upload(
            BytesIO(content),
            "test/document.pdf",
        )

        metadata = await storage.get_metadata("test/document.pdf")
        assert metadata is not None
        assert metadata.size == len(content)
