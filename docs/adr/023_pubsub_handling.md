# ADR 023: Pub/Sub Message Handling (Future)

## Status
**Proposed** - 2026-03-02 (Not yet implemented)

## Context
The reference implementation processes documents via Google Cloud Pub/Sub push subscriptions. Messages arrive as base64-encoded JSON payloads wrapped in Pub/Sub envelope format. The system uses ACK/NACK semantics for reliable message processing.

## Purpose
Enable asynchronous, event-driven document processing at scale. Instead of synchronous HTTP upload, documents are queued and processed with guaranteed delivery and automatic retry on transient failures.

## Alternatives Considered

| Alternative | Delivery | Ordering | Cost | Complexity |
|-------------|----------|----------|------|------------|
| **Pub/Sub push (Planned)** | At-least-once | No | Low | Medium |
| Pub/Sub pull | At-least-once | Optional | Low | Medium |
| AWS SQS | At-least-once | FIFO option | Low | Medium |
| Redis Queue (RQ) | Best-effort | FIFO | Free | Low |
| Celery + RabbitMQ | At-least-once | FIFO | Free | High |
| Kafka | Exactly-once | Yes | High | High |

## Planned Implementation

### Message Format

Pub/Sub push messages arrive wrapped:

```json
{
  "message": {
    "attributes": {
      "eventName": "document.uploaded",
      "actorType": "system",
      "actorId": "upload-service"
    },
    "data": "base64-encoded-json"
  },
  "subscription": "projects/my-project/subscriptions/doc-processing"
}
```

The `data` field decodes to:

```json
{
  "bucket": "user-uploads-prod",
  "name": "loan_application_001.pdf",
  "path": "uploads/2026/03/02",
  "documentType": "loan_application",
  "businessId": "12345",
  "uploadId": "67890",
  "fileSize": 1048576,
  "mimeType": "application/pdf"
}
```

### Endpoint

```python
@router.post("/process_message")
async def process_message(request: Request):
    """Handle Pub/Sub push subscription."""
    body = await request.json()
    push_message = PubSubPushMessage(**body)  # Validates + decodes base64
    payload = convert_to_processing_payload(push_message)
    await processor.process(payload)
    return JSONResponse(status_code=200, content={"status": "acknowledged"})
```

### ACK/NACK Strategy

This is the critical design decision. Pub/Sub interprets HTTP status codes as:
- **2xx**: ACK — message successfully processed, remove from queue
- **4xx/5xx**: NACK — message failed, retry with exponential backoff

| Error Type | HTTP Response | Pub/Sub Behavior | Rationale |
|------------|---------------|-------------------|-----------|
| Invalid document (bad format, password-protected) | 200 (ACK) | No retry | Unrecoverable — retrying won't help |
| LLM failure (timeout, rate limit) | 500 (NACK) | Retry with backoff | Transient — likely succeeds later |
| Internal error (bug, config issue) | 500 (NACK) | Retry with backoff | Transient — deploy fix, retry works |

### Why ACK on 4xx Errors

This is counter-intuitive but critical. If a document is corrupted or password-protected, no amount of retrying will fix it. Returning 200 (ACK) tells Pub/Sub to stop retrying and prevents the message from becoming a "poison pill" that blocks the queue indefinitely.

The error is still captured via:
1. Error archiving to cloud storage (ADR 022)
2. Sentry error tracking
3. Prometheus metrics (`validation_failures_total`)

### Dead Letter Queue

After max retries (configured in Pub/Sub subscription), messages are forwarded to a Dead Letter Topic for manual investigation:

```
Main Topic → Subscription (max 5 retries, exponential backoff)
                  ↓ (on max retries exceeded)
              Dead Letter Topic → DLQ Subscription → Manual review
```

### Bucket Allowlist (SSRF Protection)

The reference implementation validates that the bucket in the payload is in an allowlist:

```python
ALLOWED_BUCKETS = {
    "user-uploads-production",
    "user-uploads-staging",
    "user-uploads-dev",
}

def validate_allowed_bucket(payload):
    if payload.data.bucket not in settings.ALLOWED_BUCKETS:
        raise HTTPException(status_code=400, detail="Bucket not allowed")
```

This prevents SSRF attacks where a malicious message could trick the service into reading from arbitrary GCS buckets.

## Conclusion
Pub/Sub push is the right pattern for GCP-native async processing. The ACK/NACK pattern with DLQ provides resilient message handling without custom retry logic. The bucket allowlist is a critical security measure.

## Consequences

### Positive
- Decouples upload from processing (async)
- Automatic retry with exponential backoff
- Dead letter queue for failed messages
- At-least-once delivery guarantee
- Scales horizontally via Cloud Run

### Negative
- More complex than synchronous HTTP
- At-least-once means idempotency is required
- Pub/Sub subscription configuration needed
- Message format adds parsing overhead

## Implementation Timeline
Phase 2: After MVP submission. Requires GCP Pub/Sub topic + subscription configuration and `google-cloud-pubsub` dependency.
