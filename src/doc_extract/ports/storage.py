"""Storage port - abstraction for blob storage operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO


@dataclass
class StorageMetadata:
    """Metadata about a stored file."""

    path: str
    size: int
    content_type: str
    created_at: datetime
    checksum: str | None = None


class BlobStoragePort(ABC):
    """Port for blob storage operations.

    This abstract base class defines the contract for all storage implementations.
    It follows the Port & Adapter pattern from Hexagonal Architecture.

    Implementations:
        - LocalFileSystemAdapter: For local development
        - GCSStorageAdapter: For production (Google Cloud Storage)
    """

    @abstractmethod
    async def upload(
        self,
        file_data: BinaryIO,
        destination_path: str,
        content_type: str | None = None,
    ) -> StorageMetadata:
        """Upload a file to storage.

        Args:
            file_data: Binary stream of the file
            destination_path: Path where file should be stored
            content_type: MIME type of the file

        Returns:
            StorageMetadata with file details
        """
        pass

    @abstractmethod
    async def download(self, source_path: str) -> bytes:
        """Download a file from storage.

        Args:
            source_path: Path to the file

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Path to the file

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: Path to check

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def generate_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str:
        """Generate a signed URL for temporary access.

        Args:
            path: Path to the file
            expiration_seconds: URL validity duration

        Returns:
            Signed URL string
        """
        pass

    @abstractmethod
    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file.

        Args:
            path: Path to the file

        Returns:
            StorageMetadata or None if not found
        """
        pass
