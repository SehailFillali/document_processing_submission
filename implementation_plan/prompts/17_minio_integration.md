# Prompt 17: MinIO Blob Storage Integration

## Status
[COMPLETED]

## Context

We need to simulate production blob storage behavior using MinIO (S3-compatible) in Docker. In production, files will be uploaded to S3 or GCS, and our system will receive messages from Pub/Sub or HTTP requests with URIs pointing to the document location in blob storage.

This prompt adds:
1. MinIO container in docker-compose
2. MinIOAdapter implementing BlobStoragePort  
3. New endpoint to process files from blob storage URIs (s3://, minio://, gs://)
4. Configuration to switch between local storage and MinIO
5. Test documents mounted to MinIO

## Objective

Create a complete MinIO integration that:
- Is fully compatible with existing code (NO REGRESSION)
- Simulates production S3/GCS behavior
- Provides a new endpoint for blob storage URI processing
- Can switch between local filesystem and MinIO via configuration

## Requirements

### 1. Update docker-compose.yml

Add MinIO service with proper configuration:

```yaml
services:
  # ... existing services ...

  minio:
    image: minio/minio:latest
    container_name: doc-extract-minio
    ports:
      - "9000:9000"      # API port
      - "9001:9001"      # Console port
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
      - ./tests/evaluation/data:/mnt/data/documents  # Mount test documents
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    profiles:
      - minio

volumes:
  # ... existing volumes ...
  minio_data:
```

**CRITICAL:** The MinIO service MUST use `profiles: ["minio"]` so it only starts when explicitly enabled with `docker-compose --profile minio up`.

### 2. Create MinIO Adapter

File: `src/doc_extract/adapters/minio_adapter.py`

This adapter MUST implement the exact same interface as `BlobStoragePort`:

```python
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
from datetime import datetime, timedelta
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
        # Import minio here to make it optional
        try:
            from minio import Minio
            from minio.error import S3Error
            self._minio_available = True
            self._S3Error = S3Error
        except ImportError:
            logger.warning("MinIO library not installed. Install with: uv add minio")
            self._minio_available = False
            self._S3Error = None
        
        # Get configuration from environment or parameters
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.secure = secure or os.getenv("MINIO_SECURE", "false").lower() == "true"
        self.bucket_name = bucket_name or os.getenv("MINIO_BUCKET_NAME", "documents")
        
        # Initialize MinIO client
        if self._minio_available:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            # Ensure bucket exists
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
                # Just bucket name, no object
                return rest, ""
        else:
            # Plain path - use default bucket
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
        
        # Parse destination path
        bucket, object_name = self._parse_uri(destination_path)
        
        # Upload to MinIO
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
                created_at=datetime.utcnow(),
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
            raise FileNotFoundError(f"File not found: {source_path}")

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
                checksum=stat.etag.replace('"', ''),  # ETag is MD5 in quotes
            )
        except self._S3Error:
            return None
```

### 3. Update Configuration

File: `src/doc_extract/core/config.py`

Add MinIO configuration to existing Settings:

```python
"""Configuration management using pydantic-settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ... existing settings ...

    # Storage Configuration
    storage_backend: str = Field(
        default="local",
        description="Storage backend: local, minio, s3, gcs"
    )
    
    # MinIO Configuration
    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO server endpoint"
    )
    minio_access_key: str = Field(
        default="minioadmin",
        description="MinIO access key"
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        description="MinIO secret key"
    )
    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO"
    )
    minio_bucket_name: str = Field(
        default="documents",
        description="Default MinIO bucket name"
    )
    
    # AWS S3 Configuration (for production)
    aws_access_key_id: str | None = Field(
        default=None,
        description="AWS access key ID"
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        description="AWS secret access key"
    )
    aws_s3_bucket: str | None = Field(
        default=None,
        description="S3 bucket name"
    )
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
settings = Settings()
```

### 4. Create Storage Factory

File: `src/doc_extract/adapters/storage_factory.py`

A factory to create the appropriate storage adapter based on configuration:

```python
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
        # Use MinIO adapter with AWS credentials
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
```

### 5. Create New Blob Storage Endpoint

File: `src/doc_extract/api/blob_endpoints.py`

New endpoint that accepts blob storage URIs:

```python
"""Blob storage endpoints for processing files from S3/GCS/MinIO."""
import hashlib
import uuid
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from doc_extract.adapters.storage_factory import get_storage_adapter
from doc_extract.core.logging import logger
from doc_extract.domain.submission import (
    DocumentMetadata,
    DocumentSubmission,
    DocumentType,
    SubmissionStatus,
)
from doc_extract.services.processing import ProcessingService

router = APIRouter(prefix="/api/v1", tags=["Blob Storage"])


class BlobUriRequest(BaseModel):
    """Request to process a document from blob storage URI."""
    
    uri: str = Field(
        ...,
        description="Blob storage URI (minio://bucket/path, s3://bucket/path, gs://bucket/path)"
    )
    document_type: str = Field(
        default="loan_application",
        description="Type of document being processed"
    )
    borrower_id: str | None = Field(
        default=None,
        description="Optional borrower ID for tracking"
    )


class BlobProcessingResponse(BaseModel):
    """Response for blob storage processing request."""
    
    submission_id: str
    status: str
    message: str
    uri: str


@router.post("/documents/process_uploaded_blob", response_model=BlobProcessingResponse)
async def process_from_blob(request: BlobUriRequest):
    """Process a document from blob storage (S3, GCS, MinIO).
    
    The system will:
    1. Connect to the blob storage using the URI scheme
    2. Download the document
    3. Process it using the extraction pipeline
    4. Return the submission ID for tracking
    
    Supported URI schemes:
    - minio://bucket/object - Local MinIO
    - s3://bucket/object   - AWS S3
    - gs://bucket/object  - Google Cloud Storage
    
    Example:
        minio://documents/loan-app-123.pdf
        s3://my-bucket/invoices/2024/abc.pdf
        gs://project-bucket/loan-docs/def.pdf
    """
    try:
        # Validate URI
        uri = request.uri
        if not uri or "://" not in uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid blob URI. Must include scheme (minio://, s3://, gs://)"
            )
        
        # Get storage adapter based on URI scheme
        storage = get_storage_adapter()
        
        # Check if file exists
        if not await storage.exists(uri):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found at URI: {uri}"
            )
        
        # Get file metadata
        metadata = await storage.get_metadata(uri)
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not retrieve metadata for: {uri}"
            )
        
        # Download file content
        content = await storage.download(uri)
        
        # Generate submission ID
        submission_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        
        # Compute hash
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Create document metadata
        doc_metadata = DocumentMetadata(
            document_id=document_id,
            file_hash=file_hash,
            file_name=uri.split("/")[-1],  # Extract filename from URI
            file_size=len(content),
            mime_type=metadata.content_type,
            document_type=DocumentType(request.document_type),
        )
        
        # Create submission (store metadata only, not file content)
        from doc_extract.api.main import submissions_db
        
        submission = DocumentSubmission(
            submission_id=submission_id,
            status=SubmissionStatus.PROCESSING,
            documents=[doc_metadata],
        )
        
        submissions_db[submission_id] = submission
        
        # Trigger processing with the downloaded content
        try:
            from io import BytesIO
            from doc_extract.adapters.local_storage import LocalFileSystemAdapter
            
            # Temporarily save to local storage for processing
            temp_storage = LocalFileSystemAdapter(base_path="./uploads")
            temp_path = f"{submission_id}/{document_id}_{doc_metadata.file_name}"
            await temp_storage.upload(
                BytesIO(content),
                temp_path,
                content_type=metadata.content_type,
            )
            
            # Process
            processor = ProcessingService()
            result = await processor.process_submission(submission_id, temp_path)
            
            if result.get("status") == "success":
                submission.status = SubmissionStatus.COMPLETED
                submission.borrower_profile_id = result.get("data")
            else:
                submission.status = SubmissionStatus.FAILED
                submission.error_message = result.get("error", "Processing failed")
                
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            submission.status = SubmissionStatus.FAILED
            submission.error_message = str(e)
        
        logger.info(f"Blob document processed: {submission_id}")
        
        return BlobProcessingResponse(
            submission_id=submission_id,
            status=submission.status.value,
            message=f"Document from {uri} processed successfully",
            uri=uri,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blob processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )


@router.get("/blob/health")
async def blob_storage_health():
    """Check blob storage connectivity."""
    try:
        storage = get_storage_adapter()
        # Try to list buckets (will raise if not connected)
        if hasattr(storage, 'client'):
            # For MinIO, try to list buckets
            buckets = storage.client.list_buckets()
            return {
                "status": "healthy",
                "backend": settings.storage_backend,
                "endpoint": settings.minio_endpoint,
                "bucket": settings.minio_bucket_name,
            }
        return {"status": "unknown", "backend": settings.storage_backend}
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "backend": settings.storage_backend,
        }
```

### 6. Update API Main

File: `src/doc_extract/api/main.py`

Add the new blob endpoints to the existing API:

```python
"""FastAPI main application and routes."""

# ... existing imports ...

# Add blob endpoints router
from doc_extract.api.blob_endpoints import router as blob_router

# ... existing app setup ...

# Include blob storage endpoints
app.include_router(blob_router)

# ... rest of existing code ...
```

### 7. Update .env.example

Add MinIO configuration:

```bash
# Storage Backend: local, minio, s3, gcs
STORAGE_BACKEND=local

# MinIO Configuration (when STORAGE_BACKEND=minio)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET_NAME=documents

# AWS S3 Configuration (when STORAGE_BACKEND=s3)
# AWS_ACCESS_KEY_ID=your_access_key
# AWS_SECRET_ACCESS_KEY=your_secret_key
# AWS_S3_BUCKET=your-bucket-name
# AWS_REGION=us-east-1
```

### 8. Create Test Documents

Create sample PDF files in `tests/evaluation/data/` for MinIO testing:

```
tests/evaluation/data/
├── sample_loan_1.pdf
├── sample_loan_2.pdf
└── ground_truth/
    ├── sample_loan_1_truth.json
    └── sample_loan_2_truth.json
```

### 9. Update pyproject.toml

Add MinIO dependency:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "minio>=7.2.0",
]
```

### 10. Create Test File for MinIO

File: `tests/test_minio_adapter.py`:

```python
"""Tests for MinIO adapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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

    @pytest.mark.asyncio
    async def test_process_from_blob_invalid_uri(self):
        """Test blob endpoint with invalid URI."""
        from fastapi.testclient import TestClient
        from doc_extract.api.main import app
        
        client = TestClient(app)
        
        response = client.post(
            "/api/v1/documents/process_uploaded_blob",
            json={"uri": "not-a-valid-uri", "document_type": "loan_application"}
        )
        
        assert response.status_code == 400

    def test_blob_health_endpoint(self):
        """Test blob storage health check."""
        from fastapi.testclient import TestClient
        from doc_extract.api.main import app
        
        client = TestClient(app)
        
        response = client.get("/api/v1/blob/health")
        
        # Should return even if MinIO not available
        assert response.status_code == 200
```

## Deliverables

- [ ] docker-compose.yml updated with MinIO service (with profiles)
- [ ] src/doc_extract/adapters/minio_adapter.py created
- [ ] src/doc_extract/adapters/storage_factory.py created
- [ ] src/doc_extract/core/config.py updated with MinIO config
- [ ] src/doc_extract/api/blob_endpoints.py created
- [ ] src/doc_extract/api/main.py updated to include blob router
- [ ] .env.example updated with MinIO variables
- [ ] pyproject.toml updated with minio dependency
- [ ] tests/test_minio_adapter.py created
- [ ] Test documents in tests/evaluation/data/ (or existing documents used)

## Success Criteria

1. **MinIO starts** with `docker-compose --profile minio up`
2. **New endpoint works**: `POST /api/v1/documents/process_uploaded_blob` accepts minio://, s3://, gs:// URIs
3. **Storage switching**: Can switch between local and MinIO via STORAGE_BACKEND env var
4. **No regression**: Existing `/api/v1/documents/upload` continues to work
5. **Tests pass**: New tests pass, existing tests still pass

## Environment Variables Summary

| Variable | Default | Description |
|----------|---------|-------------|
| STORAGE_BACKEND | local | Storage type: local, minio, s3, gcs |
| MINIO_ENDPOINT | localhost:9000 | MinIO server |
| MINIO_ACCESS_KEY | minioadmin | MinIO access key |
| MINIO_SECRET_KEY | minioadmin | MinIO secret key |
| MINIO_BUCKET_NAME | documents | Default bucket |
| AWS_ACCESS_KEY_ID | None | AWS access key (for s3) |
| AWS_SECRET_ACCESS_KEY | None | AWS secret key (for s3) |
| AWS_S3_BUCKET | None | S3 bucket name (for s3) |

## Testing Instructions

```bash
# 1. Start MinIO
docker-compose --profile minio up -d

# 2. Upload test document to MinIO (via MinIO console or mc CLI)
# Console: http://localhost:9001 (minioadmin/minioadmin)
# Or: mc cp tests/evaluation/data/sample.pdf local/documents/

# 3. Set environment
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=localhost:9000

# 4. Test the new endpoint
curl -X POST http://localhost:8000/api/v1/documents/process_uploaded_blob \
  -H "Content-Type: application/json" \
  -d '{"uri": "minio://documents/sample.pdf", "document_type": "loan_application"}'

# 5. Check health
curl http://localhost:8000/api/v1/blob/health

# 6. Run tests
pytest tests/test_minio_adapter.py -v
```

## Important Notes

1. **Backward Compatibility**: The existing `/api/v1/documents/upload` endpoint must continue to work exactly as before
2. **No Breaking Changes**: All existing functionality must remain intact
3. **Error Handling**: Graceful errors when MinIO is not available
4. **URI Scheme Support**: Must handle minio://, s3://, and gs:// URIs
5. **Configuration**: Storage backend must be configurable via environment variable

## Code Snippets to Include

All code snippets above are complete and ready to copy-paste. Each file includes:
- Comprehensive docstrings
- Type hints throughout
- Error handling
- Logging
- Configuration via environment variables

## Next Steps

After this prompt completes:
1. Test MinIO integration manually
2. Add more test cases
3. Document the new endpoint in README
