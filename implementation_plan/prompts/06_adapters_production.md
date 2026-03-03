# Prompt 06: Production Adapters - Cloud Scaffolding

## Status
[PARTIALLY_IMPLEMENTED] - missing BigQuery adapter

## Context
Creating scaffolding for production adapters (GCS, Pub/Sub, BigQuery) that will be documented but not fully executed in MVP.

## Objective
Write production-ready adapter classes that are documented and structured, suitable for production use but marked as scaffolding.

## Requirements

### 1. Create GCS Storage Adapter Scaffolding
File: `src/doc_extract/adapters/gcs_storage.py`

```python
"""Google Cloud Storage adapter - PRODUCTION SCAFFOLDING.

This module provides the production implementation of BlobStoragePort
using Google Cloud Storage. It is provided as scaffolding and documentation
for production deployment but not executed in the MVP.

To activate in production:
1. Set GOOGLE_CLOUD_PROJECT and GCS_BUCKET_NAME env vars
2. Ensure service account has storage.objectAdmin role
3. Swap LocalFileSystemAdapter for GCSStorageAdapter in dependency injection

Architecture Decision: See docs/adr/002_storage_strategy.md
"""
from typing import BinaryIO
from datetime import datetime, timedelta
from doc_extract.ports.storage import BlobStoragePort, StorageMetadata
from doc_extract.core.logging import logger

# Note: google-cloud-storage is not in MVP dependencies
# Add to pyproject.toml production group when deploying
try:
    from google.cloud import storage
    from google.cloud.storage import Blob
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage not installed. GCSStorageAdapter is scaffolding only.")


class GCSStorageAdapter(BlobStoragePort):
    """Google Cloud Storage implementation - PRODUCTION SCAFFOLDING.
    
    This adapter implements the BlobStoragePort using Google Cloud Storage.
    It provides:
    - Scalable object storage
    - Signed URLs for temporary access
    - Lifecycle management
    - Versioning support
    
    Usage (when activated):
        storage = GCSStorageAdapter(
            bucket_name="my-extraction-bucket",
            project_id="my-gcp-project"
        )
        await storage.upload(file_data, "documents/loan.pdf")
    
    ADR Reference: docs/adr/002_storage_strategy.md
    """
    
    def __init__(
        self, 
        bucket_name: str | None = None,
        project_id: str | None = None
    ):
        if not GCS_AVAILABLE:
            raise ImportError(
                "google-cloud-storage required. "
                "Install with: uv add google-cloud-storage"
            )
        
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        
        if not self.bucket_name:
            raise ValueError("bucket_name or GCS_BUCKET_NAME env var required")
        
        # Initialize GCS client
        self.client = storage.Client(project=self.project_id)
        self.bucket = self.client.bucket(self.bucket_name)
        
        logger.info(
            f"Initialized GCSStorageAdapter: "
            f"bucket={self.bucket_name}, project={self.project_id}"
        )
    
    async def upload(
        self, 
        file_data: BinaryIO, 
        destination_path: str,
        content_type: str | None = None
    ) -> StorageMetadata:
        """Upload file to GCS bucket."""
        blob = self.bucket.blob(destination_path)
        
        # Upload content
        content = file_data.read()
        blob.upload_from_string(content, content_type=content_type)
        
        # Calculate checksum
        import hashlib
        checksum = hashlib.sha256(content).hexdigest()
        
        metadata = StorageMetadata(
            path=f"gs://{self.bucket_name}/{destination_path}",
            size=len(content),
            content_type=content_type or blob.content_type or "application/octet-stream",
            created_at=datetime.utcnow(),
            checksum=checksum
        )
        
        logger.info(f"Uploaded to GCS: {destination_path} ({metadata.size} bytes)")
        return metadata
    
    async def download(self, source_path: str) -> bytes:
        """Download file from GCS.
        
        Accepts both gs:// URLs and bucket-relative paths.
        """
        # Parse gs:// URL or use as-is
        if source_path.startswith("gs://"):
            parts = source_path[5:].split("/", 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else ""
            blob = self.client.bucket(bucket_name).blob(blob_path)
        else:
            blob = self.bucket.blob(source_path)
        
        return blob.download_as_bytes()
    
    async def delete(self, path: str) -> bool:
        """Delete file from GCS."""
        blob = self.bucket.blob(path)
        blob.delete()
        logger.info(f"Deleted from GCS: {path}")
        return True
    
    async def exists(self, path: str) -> bool:
        """Check if file exists in GCS."""
        blob = self.bucket.blob(path)
        return blob.exists()
    
    async def generate_signed_url(
        self, 
        path: str, 
        expiration_seconds: int = 3600
    ) -> str:
        """Generate signed URL for temporary access.
        
        Requires service account with appropriate IAM permissions:
        - roles/storage.objectViewer (for read access)
        - Service account must have Service Account Token Creator role
        """
        blob = self.bucket.blob(path)
        
        expiration = datetime.utcnow() + timedelta(seconds=expiration_seconds)
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET"
        )
        
        logger.info(f"Generated signed URL for {path}, expires in {expiration_seconds}s")
        return url
    
    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get GCS blob metadata."""
        blob = self.bucket.blob(path)
        
        if not blob.exists():
            return None
        
        blob.reload()  # Fetch metadata
        
        return StorageMetadata(
            path=f"gs://{self.bucket_name}/{path}",
            size=blob.size or 0,
            content_type=blob.content_type or "application/octet-stream",
            created_at=blob.time_created or datetime.utcnow(),
            checksum=blob.md5_hash
        )
```

### 2. Create Pub/Sub Queue Adapter Scaffolding
File: `src/doc_extract/adapters/pubsub_queue.py`

```python
"""Google Pub/Sub queue adapter - PRODUCTION SCAFFOLDING.

This module provides the production implementation of QueuePort
using Google Cloud Pub/Sub for distributed message queuing.

Architecture Decision: See docs/adr/005_event_driven_design.md

Scaling Considerations:
- Pub/Sub supports millions of messages per second
- Automatic load balancing across subscribers
- At-least-once delivery guarantee
- Dead letter topics for failed messages
"""
from typing import Callable, Any
from doc_extract.ports.queue import (
    QueuePort, QueueMessage, QueueSubscription
)
from doc_extract.core.logging import logger

try:
    from google.cloud import pubsub_v1
    PUBSUB_AVAILABLE = True
except ImportError:
    PUBSUB_AVAILABLE = False
    logger.warning("google-cloud-pubsub not installed. PubSubAdapter is scaffolding only.")


class PubSubAdapter(QueuePort):
    """Google Pub/Sub implementation - PRODUCTION SCAFFOLDING.
    
    Provides distributed, scalable message queuing for the extraction pipeline.
    
    IAM Requirements:
    - roles/pubsub.publisher (for publishing)
    - roles/pubsub.subscriber (for subscribing)
    - roles/pubsub.viewer (for topic/subscription management)
    
    Usage (when activated):
        queue = PubSubAdapter(project_id="my-project")
        await queue.publish("document-uploads", {"id": "123", "action": "process"})
    """
    
    def __init__(self, project_id: str | None = None):
        if not PUBSUB_AVAILABLE:
            raise ImportError(
                "google-cloud-pubsub required. "
                "Install with: uv add google-cloud-pubsub"
            )
        
        import os
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        
        if not self.project_id:
            raise ValueError("project_id or GOOGLE_CLOUD_PROJECT env var required")
        
        self.publisher = pubsub_v1.PublisherClient()
        self.subscriber = pubsub_v1.SubscriberClient()
        
        # Track subscriptions for cleanup
        self._streaming_pulls = []
        
        logger.info(f"Initialized PubSubAdapter for project {self.project_id}")
    
    def _get_topic_path(self, topic: str) -> str:
        """Get full topic path."""
        return self.publisher.topic_path(self.project_id, topic)
    
    def _get_subscription_path(self, subscription: str) -> str:
        """Get full subscription path."""
        return self.subscriber.subscription_path(self.project_id, subscription)
    
    async def publish(self, topic: str, message: dict) -> str:
        """Publish message to Pub/Sub topic."""
        import json
        from google.api_core.exceptions import NotFound
        
        topic_path = self._get_topic_path(topic)
        
        # Ensure topic exists (create if not)
        try:
            self.publisher.get_topic(request={"topic": topic_path})
        except NotFound:
            self.publisher.create_topic(request={"name": topic_path})
            logger.info(f"Created Pub/Sub topic: {topic}")
        
        # Publish message
        data = json.dumps(message).encode("utf-8")
        future = self.publisher.publish(topic_path, data)
        message_id = future.result()
        
        logger.info(f"Published message {message_id} to topic {topic}")
        return message_id
    
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[QueueMessage], Any],
        subscription_name: str | None = None,
        **kwargs
    ) -> QueueSubscription:
        """Subscribe to a Pub/Sub topic.
        
        Creates a pull subscription and starts streaming messages.
        """
        import json
        import uuid
        from concurrent.futures import TimeoutError
        
        topic_path = self._get_topic_path(topic)
        subscription_id = subscription_name or f"{topic}-sub-{uuid.uuid4().hex[:8]}"
        subscription_path = self._get_subscription_path(subscription_id)
        
        # Create subscription if not exists
        from google.api_core.exceptions import AlreadyExists
        try:
            self.subscriber.create_subscription(
                request={"name": subscription_path, "topic": topic_path}
            )
            logger.info(f"Created subscription: {subscription_id}")
        except AlreadyExists:
            logger.info(f"Using existing subscription: {subscription_id}")
        
        # Message callback
        def callback(message):
            try:
                data = json.loads(message.data.decode("utf-8"))
                queue_msg = QueueMessage(
                    message_id=message.message_id,
                    body=data,
                    timestamp=message.publish_time,
                    attempts=message.delivery_attempt or 0,
                    metadata={"topic": topic, "subscription": subscription_id}
                )
                
                # Call handler
                import asyncio
                asyncio.create_task(handler(queue_msg))
                
                # Acknowledge
                message.ack()
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                message.nack()
        
        # Start streaming pull
        streaming_pull_future = self.subscriber.subscribe(
            subscription_path, callback=callback
        )
        self._streaming_pulls.append(streaming_pull_future)
        
        logger.info(f"Subscribed to {topic} with subscription {subscription_id}")
        
        return QueueSubscription(subscription_id=subscription_id)
    
    async def acknowledge(self, message_id: str) -> bool:
        """Acknowledge is handled automatically in streaming pull."""
        logger.debug(f"Acknowledge called for {message_id} (handled by Pub/Sub)")
        return True
    
    async def reject(
        self, 
        message_id: str, 
        requeue: bool = False,
        reason: str | None = None
    ) -> bool:
        """Reject/negative acknowledge."""
        # In Pub/Sub, this is handled by not acking (message redelivered)
        logger.warning(f"Message {message_id} rejected: {reason}")
        if not requeue:
            # Move to DLQ (would require DLQ topic configuration)
            pass
        return True
    
    async def publish_to_dlq(
        self, 
        message: QueueMessage, 
        reason: str
    ) -> str:
        """Publish to Dead Letter Queue topic."""
        dlq_topic = f"{message.metadata.get('topic', 'unknown')}-dlq"
        
        dlq_message = {
            "original_message": message.body,
            "original_message_id": message.message_id,
            "failure_reason": reason,
            "attempts": message.attempts,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await self.publish(dlq_topic, dlq_message)
```

### 3. Create BigQuery Adapter Scaffolding
File: `src/doc_extract/adapters/bigquery_db.py`

```python
"""BigQuery database adapter - PRODUCTION SCAFFOLDING.

This module provides the production implementation of DatabasePort
using Google BigQuery for analytics and data warehousing.

Data Strategy:
- Raw extraction results stored in GCS (JSON)
- BigQuery for querying, aggregating, reporting
- Schema: extraction_results table with nested structures

Note: BigQuery is append-only by design. Updates are simulated using
inserts with deduplication in queries.
"""
from typing import Any
from datetime import datetime
from doc_extract.ports.database import (
    DatabasePort, QueryFilter, QueryResult
)
from doc_extract.core.logging import logger

try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    logger.warning("google-cloud-bigquery not installed. BigQueryAdapter is scaffolding only.")


class BigQueryAdapter(DatabasePort):
    """BigQuery implementation - PRODUCTION SCAFFOLDING.
    
    Provides scalable data warehousing for extraction results.
    
    Schema Design:
        Table: extraction_results
        - submission_id (STRING, required)
        - borrower_profile (RECORD, nested)
        - source_documents (REPEATED STRING)
        - extraction_confidence (FLOAT)
        - created_at (TIMESTAMP)
        - _loaded_at (TIMESTAMP)
    
    IAM Requirements:
    - roles/bigquery.dataEditor
    - roles/bigquery.jobUser
    """
    
    def __init__(
        self,
        project_id: str | None = None,
        dataset_id: str = "extraction",
        table_id: str = "results"
    ):
        if not BIGQUERY_AVAILABLE:
            raise ImportError(
                "google-cloud-bigquery required. "
                "Install with: uv add google-cloud-bigquery"
            )
        
        import os
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset_id = dataset_id
        self.table_id = table_id
        
        self.client = bigquery.Client(project=self.project_id)
        self.table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        
        logger.info(f"Initialized BigQueryAdapter: {self.table_ref}")
    
    async def create(self, table: str, data: dict) -> str:
        """Insert row into BigQuery.
        
        Note: BigQuery is append-only. This always inserts.
        """
        import json
        from google.cloud import bigquery
        
        # Generate ID if not provided
        record_id = data.get("id") or data.get("submission_id") or str(uuid.uuid4())
        
        # Prepare row
        row = {
            "submission_id": record_id,
            "data": json.dumps(data),
            "_loaded_at": datetime.utcnow().isoformat()
        }
        
        # Insert
        errors = self.client.insert_rows_json(self.table_ref, [row])
        
        if errors:
            logger.error(f"BigQuery insert errors: {errors}")
            raise Exception(f"Insert failed: {errors}")
        
        logger.info(f"Inserted row {record_id} into {self.table_ref}")
        return record_id
    
    async def read(self, table: str, record_id: str) -> dict | None:
        """Query BigQuery for specific record.
        
        Uses deduplication query (latest record wins).
        """
        import json
        
        query = f"""
        SELECT data, _loaded_at
        FROM `{self.table_ref}`
        WHERE submission_id = @submission_id
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY submission_id 
            ORDER BY _loaded_at DESC
        ) = 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("submission_id", "STRING", record_id)
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            data = json.loads(row.data)
            data["id"] = record_id
            return data
        
        return None
    
    async def update(self, table: str, record_id: str, data: dict) -> bool:
        """Update is simulated by inserting new row.
        
        BigQuery is append-only. Latest row wins in queries.
        """
        # Read existing to merge
        existing = await self.read(table, record_id)
        if existing:
            existing.update(data)
            data = existing
        
        data["id"] = record_id
        await self.create(table, data)
        return True
    
    async def upsert(self, table: str, record_id: str, data: dict) -> str:
        """Upsert = insert (BigQuery handles deduplication in queries)."""
        data["id"] = record_id
        return await self.create(table, data)
```

## Deliverables
- [ ] adapters/gcs_storage.py with GCSStorageAdapter (scaffolding)
- [ ] adapters/pubsub_queue.py with PubSubAdapter (scaffolding)
- [ ] adapters/bigquery_db.py with BigQueryAdapter (scaffolding)
- [ ] All files marked as "PRODUCTION SCAFFOLDING"
- [ ] Comprehensive IAM requirements documented
- [ ] Import error handling for optional dependencies

## Documentation Requirements
Each scaffolding file must include:
1. Header comment explaining this is scaffolding
2. Architecture Decision Reference (ADR link)
3. IAM requirements for activation
4. Usage example when activated
5. Dependencies needed

## Success Criteria
- Files compile without errors (with optional dependencies commented)
- Clear documentation on how to activate in production
- IAM roles specified for each service
- Architecture Decision References included

## Next Prompt
After this completes, move to `07_api_endpoints.md` for FastAPI routes.
