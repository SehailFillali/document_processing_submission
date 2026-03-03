"""Storage adapter factory.

Creates the appropriate storage adapter based on configuration.
"""

from doc_extract.core.config import settings
from doc_extract.core.logging import logger


def get_storage_adapter():
    """Get the storage adapter based on configuration.

    Returns:
        BlobStoragePort implementation

    Raises:
        ValueError: If storage backend is unknown
    """
    backend = settings.storage_backend.lower()

    if backend == "local":
        from doc_extract.adapters.local_storage import LocalFileSystemAdapter

        logger.info("Using LocalFileSystemAdapter")
        return LocalFileSystemAdapter(base_path="./uploads")

    elif backend == "minio":
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        logger.info("Using MinIOAdapter")
        return MinIOAdapter(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            bucket_name=settings.minio_bucket_name,
        )

    elif backend == "s3":
        from doc_extract.adapters.minio_adapter import MinIOAdapter

        logger.info("Using MinIOAdapter for AWS S3")
        return MinIOAdapter(
            endpoint="s3.amazonaws.com",
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
            secure=True,
            bucket_name=settings.aws_s3_bucket,
        )

    else:
        raise ValueError(f"Unknown storage backend: {backend}")
