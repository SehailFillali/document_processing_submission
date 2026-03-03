"""Utility functions for hashing and ID generation."""

import hashlib
import uuid
from datetime import UTC, datetime


def generate_submission_id() -> str:
    """Generate a unique submission ID."""
    return str(uuid.uuid4())


def generate_document_id() -> str:
    """Generate a unique document ID."""
    return str(uuid.uuid4())


def compute_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def generate_trace_id() -> str:
    """Generate a trace ID for request tracking."""
    return f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
