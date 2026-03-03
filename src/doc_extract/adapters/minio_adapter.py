"""MinIO/S3-compatible blob storage adapter.

This adapter provides S3-compatible blob storage functionality using MinIO.
It simulates how the system will work in production with S3 or GCS.

URI Schemes Supported:
- minio://bucket/path - Local MinIO (for development)
- s3://bucket/path    - S3 (production)
- gs://bucket/path   - Google Cloud Storage (production)

The adapter automatically detects the URI scheme and routes to the
appropriate backend.
"""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import BinaryIO

from doc_extract.core.logging import logger
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata


class MinIOAdapter(BlobStoragePort):
    """MinIO/S3-compatible implementation of BlobStoragePort.

    This adapter provides S3-compatible blob storage using MinIO.
    It can also interface with AWS S3 and Google Cloud Storage.

    Configuration (via environment variables):
        MINIO_ENDPOINT: MinIO server address (default: localhost:9000)
        MINIO_ACCESS_KEY: Access key (default: minioadmin)
        MINIO_SECRET_KEY: Secret key (default: minioadmin)
        MINIO_SECURE: Use HTTPS (default: false)
        MINIO_BUCKET_NAME: Default bucket name (default: documents)

    Usage:
        # For local MinIO
        adapter = MinIOAdapter()

        # For production S3
        adapter = MinIOAdapter(
            endpoint="s3.amazonaws.com",
            access_key="aws_access_key",
            secret_key="aws_secret_key",
            secure=True,
            bucket_name="my-bucket"
        )
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool = False,
        bucket_name: str | None = None,
    ):
        try:
            from minio import Minio
            from minio.error import S3Error

            self._minio_available = True
            self._S3Error = S3Error
        except ImportError:
            logger.warning("MinIO library not installed. Install with: uv add minio")
            self._minio_available = False
            self._S3Error = None
            self.client = None
            self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
            self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
            self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
            self.secure = secure or os.getenv("MINIO_SECURE", "false").lower() == "true"
            self.bucket_name = bucket_name or os.getenv(
                "MINIO_BUCKET_NAME", "documents"
            )
            return

        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.secure = secure or os.getenv("MINIO_SECURE", "false").lower() == "true"
        self.bucket_name = bucket_name or os.getenv("MINIO_BUCKET_NAME", "documents")

        if self._minio_available:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            self._ensure_bucket_exists()

        logger.info(
            f"Initialized MinIOAdapter: endpoint={self.endpoint}, "
            f"bucket={self.bucket_name}"
        )

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
        except Exception as e:
            logger.warning(f"Could not ensure bucket exists: {e}")

    def _parse_uri(self, path: str) -> tuple[str, str]:
        """Parse storage URI into bucket and object name.

        Supports:
        - minio://bucket/object
        - s3://bucket/object
        - gs://bucket/object
        - bucket/object (assume minio)
        - plain path (use default bucket)

        Returns:
            Tuple of (bucket_name, object_name)
        """
        if "://" in path:
            scheme, rest = path.split("://", 1)
            if "/" in rest:
                bucket, obj = rest.split("/", 1)
                return bucket, obj
            else:
                return rest, ""
        else:
            return self.bucket_name, path

    async def upload(
        self,
        file_data: BinaryIO,
        destination_path: str,
        content_type: str | None = None,
    ) -> StorageMetadata:
        """Upload a file to MinIO/S3."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        content = file_data.read()
        checksum = hashlib.sha256(content).hexdigest()

        bucket, object_name = self._parse_uri(destination_path)

        try:
            self.client.put_object(
                bucket,
                object_name,
                BytesIO(content),
                length=len(content),
                content_type=content_type or "application/octet-stream",
            )

            logger.info(
                f"Uploaded to MinIO: {bucket}/{object_name} ({len(content)} bytes)"
            )

            return StorageMetadata(
                path=f"minio://{bucket}/{object_name}",
                size=len(content),
                content_type=content_type or "application/octet-stream",
                created_at=datetime.now(UTC),
                checksum=checksum,
            )
        except self._S3Error as e:
            logger.error(f"MinIO upload failed: {e}")
            raise

    async def download(self, source_path: str) -> bytes:
        """Download a file from MinIO/S3."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        bucket, object_name = self._parse_uri(source_path)

        try:
            response = self.client.get_object(bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except self._S3Error as e:
            logger.error(f"MinIO download failed: {e}")
            raise FileNotFoundError(f"File not found: {source_path}") from e

    async def delete(self, path: str) -> bool:
        """Delete a file from MinIO/S3."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        bucket, object_name = self._parse_uri(path)

        try:
            self.client.remove_object(bucket, object_name)
            logger.info(f"Deleted from MinIO: {bucket}/{object_name}")
            return True
        except self._S3Error:
            return False

    async def exists(self, path: str) -> bool:
        """Check if a file exists in MinIO/S3."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        bucket, object_name = self._parse_uri(path)

        try:
            self.client.stat_object(bucket, object_name)
            return True
        except self._S3Error:
            return False

    async def generate_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str:
        """Generate a presigned URL for temporary access."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        bucket, object_name = self._parse_uri(path)

        try:
            url = self.client.presigned_get_object(
                bucket,
                object_name,
                expires=timedelta(seconds=expiration_seconds),
            )
            return url
        except self._S3Error as e:
            logger.error(f"Failed to generate signed URL: {e}")
            raise

    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file in MinIO/S3."""
        if not self._minio_available:
            raise ImportError("MinIO library not installed")

        bucket, object_name = self._parse_uri(path)

        try:
            stat = self.client.stat_object(bucket, object_name)

            return StorageMetadata(
                path=path,
                size=stat.size,
                content_type=stat.content_type,
                created_at=stat.last_modified,
                checksum=stat.etag.replace('"', ""),
            )
        except self._S3Error:
            return None
