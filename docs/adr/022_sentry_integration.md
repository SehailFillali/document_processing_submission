# ADR 022: Sentry Error Tracking Integration (Future)

## Status
**Proposed** - 2026-03-02 (Not yet implemented)

## Context
The reference implementation integrates Sentry with OpenTelemetry for error tracking with distributed trace context. This enables correlating errors with specific requests, documents, and LLM calls. It also archives errors to GCS as structured JSON for compliance.

## Purpose
Production error tracking that goes beyond logging — automatic grouping, alerting, and trace-linked error investigation. For financial document processing, error auditability is a compliance requirement.

## Alternatives Considered

| Alternative | Cost | Features | Best For |
|-------------|------|----------|----------|
| **Sentry (Planned)** | Free tier (5K events/mo) | Full tracking + tracing + alerting | Production apps |
| Logfire errors | Included | Basic error capture | Python-first |
| CloudWatch/GCP Logging | Cloud cost | Cloud-native, no setup | Single-cloud |
| Bugsnag | $$ | Good error grouping | Mobile/web |
| PagerDuty | $$$ | Alerting focused | On-call teams |

## Planned Configuration

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor, SentryPropagator

def init_sentry():
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=settings.VERSION,
            traces_sample_rate=1.0,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
            ],
            instrumenter="otel",
        )
```

## Key Feature: Error Archiving to Cloud Storage

The reference implementation archives every error to GCS as structured JSON. This provides a durable, searchable error history independent of Sentry's retention policy:

```
errors/YYYY/MM/DD/{error_id}.json
```

Each archive contains:
- `error_id`: Unique identifier
- `timestamp`: When the error occurred
- `path`: API endpoint that failed
- `error_type`: Exception class name
- `error_detail`: Exception message
- `traceback`: Full Python traceback
- `payload`: The original request body

### Why This Matters for Financial Documents
- **Compliance**: Auditors can review every failed processing attempt
- **Debugging**: Correlate errors with specific documents and payloads
- **Retry analysis**: Understand why documents failed after max retries

## Global Exception Handler Pattern

```python
async def global_exception_handler(request, exc):
    # 1. Log to Sentry
    # 2. Archive to cloud storage
    # 3. Increment error metrics
    # 4. Return appropriate response:
    #    - 4xx errors: ACK (200) to prevent Pub/Sub retries
    #    - 5xx errors: NACK (500) to trigger retries
```

## Conclusion
Sentry provides the best balance of features, ease of integration, and free tier for error tracking. The error archiving pattern is valuable for compliance in financial document processing and provides durability beyond Sentry's retention limits.

## Consequences

### Positive
- Automatic error grouping and deduplication
- Distributed trace context links errors to specific requests
- Alert rules for error spikes
- Error archiving for compliance
- Free tier sufficient for MVP

### Negative
- External dependency
- Data privacy (error payloads sent to Sentry)
- Requires SENTRY_DSN configuration

## Implementation Timeline
Phase 2: After MVP submission. Requires Sentry account setup and `sentry-sdk` dependency.
