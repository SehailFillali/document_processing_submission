"""Google Cloud Storage adapter for production."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from doc_extract.core.logging import logger
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata


class GCSStorageAdapter(BlobStoragePort):
    """Google Cloud Storage implementation of BlobStoragePort.

    Requires:
    - google-cloud-storage package
    - GOOGLE_APPLICATION_CREDENTIALS or compute engine service account

    Usage:
        storage = GCSStorageAdapter(bucket_name="my-bucket")
        await storage.upload(file_data, "documents/loan.pdf")
    """

    def __init__(
        self, bucket_name: str, project_id: str | None = None, location: str = "US"
    ):
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.location = location
        self._client = None
        self._bucket = None
        logger.info(f"Initialized GCSStorageAdapter for bucket: {bucket_name}")

    def _get_client(self):
        """Lazy initialization of GCS client."""
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client(project=self.project_id)
        return self._client

    def _get_bucket(self):
        """Lazy initialization of bucket."""
        if self._bucket is None:
            client = self._get_client()
            self._bucket = client.bucket(self.bucket_name)
        return self._bucket

    async def upload(
        self,
        file_data: BinaryIO,
        destination_path: str,
        content_type: str | None = None,
    ) -> StorageMetadata:
        """Upload file to GCS."""
        import asyncio

        content = file_data.read()
        checksum = hashlib.sha256(content).hexdigest()

        blob = self._get_bucket().blob(destination_path)

        def _upload():
            blob.upload_from_string(
                content, content_type=content_type or "application/octet-stream"
            )

        await asyncio.get_event_loop().run_in_executor(None, _upload)

        logger.info(f"Uploaded file to gs://{self.bucket_name}/{destination_path}")

        return StorageMetadata(
            path=f"gs://{self.bucket_name}/{destination_path}",
            size=len(content),
            content_type=content_type or "application/octet-stream",
            created_at=datetime.now(UTC),
            checksum=checksum,
        )

    async def download(self, source_path: str) -> bytes:
        """Download file from GCS."""
        import asyncio

        # Handle both gs:// and regular paths
        if source_path.startswith("gs://"):
            source_path = source_path.replace(f"gs://{self.bucket_name}/", "")

        blob = self._get_bucket().blob(source_path)

        def _download():
            return blob.download_as_bytes()

        return await asyncio.get_event_loop().run_in_executor(None, _download)

    async def delete(self, path: str) -> bool:
        """Delete file from GCS."""
        import asyncio

        if path.startswith("gs://"):
            path = path.replace(f"gs://{self.bucket_name}/", "")

        blob = self._get_bucket().blob(path)

        def _delete():
            blob.delete()

        try:
            await asyncio.get_event_loop().run_in_executor(None, _delete)
            logger.info(f"Deleted gs://{self.bucket_name}/{path}")
            return True
        except Exception:
            return False

    async def exists(self, path: str) -> bool:
        """Check if file exists in GCS."""
        import asyncio

        if path.startswith("gs://"):
            path = path.replace(f"gs://{self.bucket_name}/", "")

        blob = self._get_bucket().blob(path)

        def _exists():
            return blob.exists()

        return await asyncio.get_event_loop().run_in_executor(None, _exists)

    async def generate_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str:
        """Generate signed URL for temporary access."""
        import asyncio

        if path.startswith("gs://"):
            path = path.replace(f"gs://{self.bucket_name}/", "")

        blob = self._get_bucket().blob(path)

        def _generate_url():
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expiration_seconds)
            )

        return await asyncio.get_event_loop().run_in_executor(None, _generate_url)

    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file in GCS."""
        import asyncio

        if path.startswith("gs://"):
            path = path.replace(f"gs://{self.bucket_name}/", "")

        blob = self._get_bucket().blob(path)

        def _get_metadata():
            if not blob.exists():
                return None
            return {
                "size": blob.size,
                "content_type": blob.content_type,
                "updated": blob.updated,
            }

        meta = await asyncio.get_event_loop().run_in_executor(None, _get_metadata)

        if not meta:
            return None

        return StorageMetadata(
            path=f"gs://{self.bucket_name}/{path}",
            size=meta["size"],
            content_type=meta["content_type"],
            created_at=meta["updated"],
            checksum=None,
        )
