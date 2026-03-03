# ADR 006: Scaling Strategy for 10x and 100x Growth

## Status
**Accepted** - 2026-03-02

## Context
System must handle growth from 100 to 10,000 to 100,000 documents/day without major rearchitecture.

## Decision
Progressive scaling strategy with clear milestones:

| Scale | Documents/Day | Architecture | Key Components |
|-------|---------------|--------------|----------------|
| MVP | ~100 | SQLite + Local | Single instance |
| 10x | ~10,000 | Cloud Run + Pub/Sub | Auto-scaling API |
| 100x | ~100,000 | GCS + BigQuery | Distributed workers |

## Scaling Approach

### MVP → 10x
- Move to Cloud Run (auto-scale 1-100 instances)
- Add Pub/Sub for async processing
- Keep SQLite (sufficient up to 10K docs)

### 10x → 100x
- Move to GCS for blob storage
- Move to BigQuery for analytics
- Add distributed workers
- Implement caching layer

## Implementation

```hcl
# Terraform for 10x scaling
resource "google_cloud_run_service" "api" {
  autoscaling {
    min_instances = 1
    max_instances = 100
  }
}

resource "google_pubsub_subscription" "worker" {
  ack_deadline_seconds = 300
  retry_policy {
    minimum_backoff = "10s"
  }
}
```

## Consequences

- **Positive**: Clear migration path, pay as you grow
- **Negative**: Migration effort at each stage

## Review Schedule
Review quarterly to assess scaling needs.
