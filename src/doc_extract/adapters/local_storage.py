"""Local file system storage adapter for development."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from doc_extract.core.logging import logger
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata


class LocalFileSystemAdapter(BlobStoragePort):
    """Local file system implementation of BlobStoragePort.

    Stores files in a local directory structure.
    """

    def __init__(self, base_path: str = "./uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized LocalFileSystemAdapter at {base_path}")

    async def upload(
        self,
        file_data: BinaryIO,
        destination_path: str,
        content_type: str | None = None,
    ) -> StorageMetadata:
        """Upload file to local filesystem."""
        full_path = self.base_path / destination_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = file_data.read()
        full_path.write_bytes(content)

        checksum = hashlib.sha256(content).hexdigest()

        metadata = StorageMetadata(
            path=str(full_path),
            size=len(content),
            content_type=content_type or "application/octet-stream",
            created_at=datetime.now(UTC),
            checksum=checksum,
        )

        logger.info(f"Uploaded file to {destination_path} ({metadata.size} bytes)")
        return metadata

    async def download(self, source_path: str) -> bytes:
        """Download file from local filesystem."""
        if source_path.startswith(str(self.base_path)):
            full_path = Path(source_path)
        else:
            full_path = self.base_path / source_path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")

        return full_path.read_bytes()

    async def delete(self, path: str) -> bool:
        """Delete file from local filesystem."""
        full_path = self.base_path / path

        if not full_path.exists():
            return False

        full_path.unlink()
        logger.info(f"Deleted file: {path}")
        return True

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self.base_path / path
        return full_path.exists()

    async def generate_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str:
        """Generate a signed URL (file:// path for local)."""
        return f"file://{self.base_path / path}"

    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file."""
        full_path = self.base_path / path

        if not full_path.exists():
            return None

        content = full_path.read_bytes()
        stat = full_path.stat()

        return StorageMetadata(
            path=str(full_path),
            size=stat.st_size,
            content_type="application/octet-stream",
            created_at=datetime.fromtimestamp(stat.st_ctime),
            checksum=hashlib.sha256(content).hexdigest(),
        )
