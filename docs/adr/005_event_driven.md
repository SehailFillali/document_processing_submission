# ADR 005: Use Event-Driven Architecture with Pub/Sub

## Status
**Accepted** - 2026-03-02

## Context
We need async processing to prevent blocking API responses. Documents should be queued for background processing.

## Decision
We will use **async message queue** with Pub/Sub pattern:
- API publishes event after upload
- Worker subscribes and processes
- Dead Letter Queue for failures

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Pub/Sub (Chosen)** | Scalable, decoupled | Requires infra | N/A |
| In-Memory Queue | Simple | Not persistent | Dev only |
| Kafka | High throughput | Complex ops | Overkill |
| RabbitMQ | Flexible | Not managed | Extra infra |

## Implementation

```python
# API: Publish event
await queue.publish("document.uploaded", {
    "submission_id": "123",
    "document_path": "uploads/123/doc.pdf"
})

# Worker: Subscribe
async def handle_document(msg: QueueMessage):
    await process_document(msg.body)
    await queue.acknowledge(msg.message_id)

await queue.subscribe("document.uploaded", handle_document)
```

## Consequences

- **Positive**: Non-blocking API, scalable workers
- **Negative**: Complexity, eventual consistency

## Review Schedule
Review when adding more async workers.
