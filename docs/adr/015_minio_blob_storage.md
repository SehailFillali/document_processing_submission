# ADR 015: Blob Storage with MinIO

## Status
**Accepted** - 2026-03-02

## Context
We need to handle document storage for both local development and production scaling. The assignment expects the system to handle files, and we need blob storage for production. We implemented MinIO support for S3-compatible storage.

## Purpose
This decision impacts:
- **Scalability**: How we handle large document volumes
- **Development**: How we run locally
- **Production**: How we deploy at scale
- **Flexibility**: How we integrate with different clouds

## Alternatives Considered

| Alternative | Cost | Complexity | Best For |
|-------------|------|------------|----------|
| **MinIO + Local (Chosen)** | Free | Low | Dev + Prod-like |
| AWS S3 | Pay usage | Medium | AWS deployments |
| GCS | Pay usage | Medium | GCP deployments |
| Azure Blob | Pay usage | Medium | Azure deployments |
| Local filesystem | Free | Lowest | Simple dev |

## Detailed Pros and Cons

### MinIO + Local Filesystem (Chosen)

**Pros:**
- **S3-compatible** - Same API as AWS S3
- **Easy local dev** - Run locally via Docker
- **Production-ready** - Scales to production
- **Same code** - No code changes between envs
- **Free** - Open source, self-hosted
- **Multi-cloud** - Works with S3, GCS, Azure

**Cons:**
- **Self-hosted** - Need to manage infrastructure
- **Dev different** - Local setup differs slightly
- **Performance** - Not as optimized as cloud services

### AWS S3

**Pros:**
- **Fully managed** - No infrastructure to manage
- **Highly available** - 99.99% SLA
- **Scalable** - Virtually unlimited

**Cons:**
- **Cost** - Pay for storage and requests
- **AWS lock-in** - Tied to AWS ecosystem
- **Complexity** - Requires AWS credentials

### Local Filesystem

**Pros:**
- **Simplest** - No setup needed
- **Free** - No cost

**Cons:**
- **Not scalable** - Can't handle production load
- **Not portable** - Can't share across instances
- **Not cloud-native** - Doesn't work in containers well

### Google Cloud Storage

**Pros:**
- **Managed** - No infrastructure
- **Integrated** - Works with GCP services

**Cons:**
- **GCP lock-in** - Tied to Google
- **Setup complexity** - Requires GCP project

## Conclusion

We chose **MinIO for development, S3/GCS for production** because:

1. **S3-compatible** - Same API everywhere
2. **Local development** - Run MinIO via docker-compose
3. **Production flexibility** - Swap to cloud when needed
4. **No code changes** - Adapter pattern handles this
5. **Assignment requirements** - Need blob storage support

## Architecture

### Storage Adapter Pattern

```
┌─────────────┐
│   API       │
└──────┬──────┘
       │
┌──────▼──────┐
│   Storage   │  (Port)
│   Port      │
└──────┬──────┘
       │
┌──────▼──────┐
│  Adapters   │
├─────────────┤
│ LocalFS     │ - Development
│ MinIO       │ - Local production-like
│ S3          │ - AWS production
│ GCS         │ - GCP production
└─────────────┘
```

### URI Scheme Support

| Scheme | Adapter | Example |
|--------|---------|---------|
| `file://` | LocalFS | `file://./uploads/doc.pdf` |
| `minio://` | MinIO | `minio://bucket/doc.pdf` |
| `s3://` | S3 | `s3://bucket/doc.pdf` |
| `gs://` | GCS | `gs://bucket/doc.pdf` |

## API Endpoint

```python
@router.post("/api/v1/documents/process_uploaded_blob")
async def process_from_blob(request: BlobUriRequest):
    """Process document from blob storage."""
    # Supports minio://, s3://, gs:// URIs
```

## Configuration

```bash
# Local development
STORAGE_BACKEND=local

# MinIO development
STORAGE_BACKEND=minio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=documents

# Production
STORAGE_BACKEND=s3
AWS_S3_BUCKET=my-bucket
AWS_REGION=us-east-1
```

## Docker Compose

```yaml
minio:
  image: minio/minio:latest
  ports:
    - "9000:9000"
    - "9001:9001"
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: minioadmin
    MINIO_ROOT_PASSWORD: minioadmin
```

## Consequences

### Positive
- Single API for all storage backends
- Easy local development
- Production scalability
- Cloud-agnostic
- Tested with docker-compose

### Negative
- Multiple adapters to maintain
- Slight performance overhead
- Must handle adapter-specific errors

## Implementation

See:
- `src/doc_extract/adapters/minio_adapter.py` - MinIO implementation
- `src/doc_extract/adapters/gcs_storage.py` - GCS implementation
- `src/doc_extract/adapters/storage_factory.py` - Factory for adapters
- `src/doc_extract/ports/storage.py` - Storage port interface
- `docker-compose.yml` - MinIO service

## Review Schedule
Review in 6 months to assess if storage strategy meets scaling needs.