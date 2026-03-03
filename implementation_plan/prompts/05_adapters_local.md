# Prompt 05: Local Adapters - Development Implementations

## Status
[PARTIALLY_IMPLEMENTED] - missing memory_queue.py

## Context
Implementing the local development adapters for the Hexagonal Architecture ports. These are simple, in-memory or file-based implementations for MVP.

## Objective
Create working local adapters for storage, queue, database, and LLM that can be swapped for production versions later.

## Requirements

### 1. Create Local File System Storage Adapter
File: `src/doc_extract/adapters/local_storage.py`

```python
"""Local file system storage adapter for development."""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from doc_extract.ports.storage import BlobStoragePort, StorageMetadata
from doc_extract.core.logging import logger


class LocalFileSystemAdapter(BlobStoragePort):
    """Local file system implementation of BlobStoragePort.
    
    Stores files in a local directory structure.
    Signed URLs are just file:// URLs (not actually signed, just paths).
    
    Usage:
        storage = LocalFileSystemAdapter(base_path="./uploads")
        await storage.upload(file_data, "documents/loan.pdf")
    """
    
    def __init__(self, base_path: str = "./uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized LocalFileSystemAdapter at {base_path}")
    
    async def upload(
        self, 
        file_data: BinaryIO, 
        destination_path: str,
        content_type: str | None = None
    ) -> StorageMetadata:
        """Upload file to local filesystem."""
        full_path = self.base_path / destination_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read and write file
        content = file_data.read()
        full_path.write_bytes(content)
        
        # Calculate checksum
        checksum = hashlib.sha256(content).hexdigest()
        
        metadata = StorageMetadata(
            path=str(full_path),
            size=len(content),
            content_type=content_type or "application/octet-stream",
            created_at=datetime.utcnow(),
            checksum=checksum
        )
        
        logger.info(f"Uploaded file to {destination_path} ({metadata.size} bytes)")
        return metadata
    
    async def download(self, source_path: str) -> bytes:
        """Download file from local filesystem."""
        # Handle both relative and absolute paths
        if source_path.startswith(str(self.base_path)):
            full_path = Path(source_path)
        else:
            full_path = self.base_path / source_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")
        
        return full_path.read_bytes()
    
    async def delete(self, path: str) -> bool:
        """Delete file from local filesystem."""
        full_path = self.base_path / path
        
        if not full_path.exists():
            return False
        
        full_path.unlink()
        logger.info(f"Deleted file: {path}")
        return True
    
    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self.base_path / path
        return full_path.exists()
    
    async def generate_signed_url(
        self, 
        path: str, 
        expiration_seconds: int = 3600
    ) -> str:
        """Generate a 'signed' URL (just file:// URL for local dev)."""
        full_path = self.base_path / path
        
        # For local dev, just return a file:// URL
        # Note: In production, this would generate actual signed URLs
        return f"file://{full_path.absolute()}"
    
    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file."""
        full_path = self.base_path / path
        
        if not full_path.exists():
            return None
        
        content = full_path.read_bytes()
        stat = full_path.stat()
        
        return StorageMetadata(
            path=str(full_path),
            size=len(content),
            content_type="application/octet-stream",  # Could be improved
            created_at=datetime.fromtimestamp(stat.st_ctime),
            checksum=hashlib.sha256(content).hexdigest()
        )
```

### 2. Create In-Memory Queue Adapter
File: `src/doc_extract/adapters/memory_queue.py`

```python
"""In-memory message queue adapter for development."""
import asyncio
import uuid
from datetime import datetime
from typing import Callable, Any, Dict, List
from collections import defaultdict

from doc_extract.ports.queue import (
    QueuePort, QueueMessage, QueueSubscription
)
from doc_extract.core.logging import logger


class AsyncMemoryQueueAdapter(QueuePort):
    """In-memory async queue implementation for local development.
    
    This simulates a message queue using Python's asyncio.
    Not suitable for production (messages lost on restart, no persistence).
    
    Usage:
        queue = AsyncMemoryQueueAdapter()
        await queue.publish("documents", {"action": "process", "id": "123"})
    """
    
    def __init__(self):
        self._topics: Dict[str, List[QueueMessage]] = defaultdict(list)
        self._subscriptions: Dict[str, List[tuple]] = defaultdict(list)
        self._dlq: Dict[str, List[tuple]] = defaultdict(list)
        self._lock = asyncio.Lock()
        logger.info("Initialized AsyncMemoryQueueAdapter")
    
    async def publish(self, topic: str, message: dict) -> str:
        """Publish message to in-memory topic."""
        message_id = str(uuid.uuid4())
        
        queue_msg = QueueMessage(
            message_id=message_id,
            body=message,
            timestamp=datetime.utcnow(),
            attempts=0,
            metadata={"topic": topic}
        )
        
        async with self._lock:
            self._topics[topic].append(queue_msg)
        
        logger.info(f"Published message {message_id} to topic {topic}")
        
        # Notify subscribers immediately
        await self._notify_subscribers(topic, queue_msg)
        
        return message_id
    
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[QueueMessage], Any],
        **kwargs
    ) -> QueueSubscription:
        """Subscribe to a topic."""
        subscription_id = str(uuid.uuid4())
        
        async with self._lock:
            self._subscriptions[topic].append((subscription_id, handler))
        
        logger.info(f"Created subscription {subscription_id} for topic {topic}")
        
        sub = QueueSubscription(subscription_id=subscription_id)
        
        # Override unsubscribe method
        original_unsubscribe = sub.unsubscribe
        async def custom_unsubscribe():
            async with self._lock:
                self._subscriptions[topic] = [
                    (sid, h) for sid, h in self._subscriptions[topic] 
                    if sid != subscription_id
                ]
            logger.info(f"Unsubscribed {subscription_id} from {topic}")
        
        sub.unsubscribe = custom_unsubscribe
        
        return sub
    
    async def _notify_subscribers(self, topic: str, message: QueueMessage) -> None:
        """Notify all subscribers of a new message."""
        async with self._lock:
            handlers = [
                handler for sid, handler in self._subscriptions[topic]
            ]
        
        # Call handlers
        for handler in handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Handler error for message {message.message_id}: {e}")
    
    async def acknowledge(self, message_id: str) -> bool:
        """Acknowledge message (no-op for in-memory)."""
        logger.debug(f"Acknowledged message {message_id}")
        return True
    
    async def reject(
        self, 
        message_id: str, 
        requeue: bool = False,
        reason: str | None = None
    ) -> bool:
        """Reject message."""
        if requeue:
            # In a real system, we'd increment attempts and requeue
            logger.warning(f"Message {message_id} rejected with requeue: {reason}")
        else:
            logger.error(f"Message {message_id} rejected: {reason}")
        return True
    
    async def publish_to_dlq(
        self, 
        message: QueueMessage, 
        reason: str
    ) -> str:
        """Publish message to Dead Letter Queue."""
        dlq_message_id = str(uuid.uuid4())
        
        async with self._lock:
            topic = message.metadata.get("topic", "unknown")
            self._dlq[topic].append((message, reason))
        
        logger.error(f"Message {message.message_id} moved to DLQ: {reason}")
        return dlq_message_id
```

### 3. Create SQLite Database Adapter
File: `src/doc_extract/adapters/sqlite_db.py`

```python
"""SQLite database adapter for development/MVP."""
import json
import uuid
from typing import Any
from datetime import datetime

import aiosqlite

from doc_extract.ports.database import (
    DatabasePort, QueryFilter, QueryResult
)
from doc_extract.core.logging import logger


class SQLiteAdapter(DatabasePort):
    """SQLite implementation of DatabasePort for MVP.
    
    Uses aiosqlite for async operations.
    Stores data as JSON in a simple key-value table.
    
    Usage:
        db = SQLiteAdapter("./data/extraction.db")
        await db.create("submissions", {"name": "Test"})
    """
    
    def __init__(self, database_url: str = "sqlite:///./data/extraction.db"):
        # Extract path from URL
        if database_url.startswith("sqlite:///"):
            self.db_path = database_url[10:]
        else:
            self.db_path = database_url
        
        # Ensure directory exists
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        logger.info(f"Initialized SQLiteAdapter at {self.db_path}")
    
    async def _get_connection(self):
        """Get async database connection."""
        return await aiosqlite.connect(self.db_path)
    
    async def _ensure_table(self, conn, table: str) -> None:
        """Ensure table exists."""
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await conn.commit()
    
    async def create(self, table: str, data: dict) -> str:
        """Create a new record."""
        record_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        async with await self._get_connection() as conn:
            await self._ensure_table(conn, table)
            
            await conn.execute(
                f"INSERT INTO {table} (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (record_id, json.dumps(data), now, now)
            )
            await conn.commit()
        
        logger.info(f"Created record {record_id} in {table}")
        return record_id
    
    async def read(self, table: str, record_id: str) -> dict | None:
        """Read a record by ID."""
        async with await self._get_connection() as conn:
            await self._ensure_table(conn, table)
            
            async with conn.execute(
                f"SELECT data FROM {table} WHERE id = ?",
                (record_id,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return json.loads(row[0])
                return None
    
    async def update(self, table: str, record_id: str, data: dict) -> bool:
        """Update a record."""
        now = datetime.utcnow().isoformat()
        
        async with await self._get_connection() as conn:
            await self._ensure_table(conn, table)
            
            # Read existing data and merge
            existing = await self.read(table, record_id)
            if not existing:
                return False
            
            existing.update(data)
            
            await conn.execute(
                f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(existing), now, record_id)
            )
            await conn.commit()
        
        logger.info(f"Updated record {record_id} in {table}")
        return True
    
    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record."""
        async with await self._get_connection() as conn:
            await self._ensure_table(conn, table)
            
            await conn.execute(
                f"DELETE FROM {table} WHERE id = ?",
                (record_id,)
            )
            await conn.commit()
        
        logger.info(f"Deleted record {record_id} from {table}")
        return True
    
    async def query(
        self,
        table: str,
        filters: list[QueryFilter] | None = None,
        order_by: str | None = None,
        page: int = 1,
        page_size: int = 20
    ) -> QueryResult:
        """Query records with basic filtering."""
        async with await self._get_connection() as conn:
            await self._ensure_table(conn, table)
            
            # Get all records (SQLite doesn't support complex filters easily in this simple schema)
            async with conn.execute(f"SELECT id, data FROM {table}") as cursor:
                rows = await cursor.fetchall()
            
            items = []
            for row_id, row_data in rows:
                data = json.loads(row_data)
                data["id"] = row_id  # Include ID in data
                items.append(data)
            
            # Simple in-memory filtering
            if filters:
                for f in filters:
                    items = [
                        item for item in items 
                        if self._matches_filter(item, f)
                    ]
            
            # Pagination
            total = len(items)
            start = (page - 1) * page_size
            end = start + page_size
            items = items[start:end]
            
            return QueryResult(
                items=items,
                total_count=total,
                page=page,
                page_size=page_size
            )
    
    def _matches_filter(self, item: dict, filter_: QueryFilter) -> bool:
        """Check if item matches filter."""
        field_parts = filter_.field.split(".")
        value = item
        
        for part in field_parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return False
        
        if filter_.operator == "eq":
            return value == filter_.value
        elif filter_.operator == "contains":
            return filter_.value in str(value)
        # Add more operators as needed
        
        return True
    
    async def upsert(self, table: str, record_id: str, data: dict) -> str:
        """Insert or update a record."""
        existing = await self.read(table, record_id)
        
        if existing:
            await self.update(table, record_id, data)
            return record_id
        else:
            # Create with specific ID
            now = datetime.utcnow().isoformat()
            
            async with await self._get_connection() as conn:
                await self._ensure_table(conn, table)
                
                await conn.execute(
                    f"INSERT INTO {table} (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (record_id, json.dumps(data), now, now)
                )
                await conn.commit()
            
            logger.info(f"Upserted record {record_id} in {table}")
            return record_id
```

### 4. Create Gemini LLM Adapter
File: `src/doc_extract/adapters/gemini_llm.py`

```python
"""Gemini LLM adapter using PydanticAI."""
import os
from typing import Type
from pydantic import BaseModel

from pydantic_ai import Agent, DocumentUrl
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from doc_extract.ports.llm import (
    LLMPort, ExtractionRequest, ExtractionResponse, LLMError
)
from doc_extract.core.logging import logger


class GeminiAdapter(LLMPort):
    """Gemini API implementation of LLMPort.
    
    Uses PydanticAI with Gemini model for structured document extraction.
    Supports direct document URLs (gs://, https://, file://).
    
    Requires:
        GEMINI_API_KEY environment variable
    
    Usage:
        llm = GeminiAdapter()
        response = await llm.extract_structured(
            ExtractionRequest(
                document_url="gs://bucket/document.pdf",
                output_schema=BorrowerProfile
            )
        )
    """
    
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable required")
        
        # Initialize provider with API key
        self.provider = GoogleProvider(api_key=self.api_key)
        self.model = GoogleModel(model_name, provider=self.provider)
        
        logger.info(f"Initialized GeminiAdapter with model {model_name}")
    
    async def extract_structured(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data using Gemini via PydanticAI."""
        import time
        
        start_time = time.time()
        
        try:
            # Create agent with output schema
            agent = Agent(
                model=self.model,
                system_prompt=request.system_prompt or self._default_system_prompt(),
                output_type=request.output_schema,
            )
            
            # Create DocumentUrl from the document URL
            # This supports gs://, https://, and file:// URLs
            doc_url = DocumentUrl(url=request.document_url)
            
            # Run extraction
            result = await agent.run([
                f"Extract structured data from this {request.document_type} document.",
                doc_url
            ])
            
            processing_time = time.time() - start_time
            
            # Calculate confidence (Gemini doesn't provide this directly, estimate)
            confidence = 0.85  # Default high confidence for Gemini
            
            # Build response
            return ExtractionResponse(
                extracted_data=result.output,
                raw_output=result.output.model_dump_json() if hasattr(result.output, 'model_dump_json') else str(result.output),
                token_usage={
                    "input_tokens": getattr(result, 'input_tokens', 0),
                    "output_tokens": getattr(result, 'output_tokens', 0),
                },
                confidence_score=confidence,
                processing_time_seconds=processing_time,
                model_name=self.model_name
            )
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            
            # Determine if error is recoverable
            error_msg = str(e).lower()
            recoverable = any([
                "rate limit" in error_msg,
                "timeout" in error_msg,
                "temporary" in error_msg
            ])
            
            raise LLMError(
                error_type="EXTRACTION_FAILED",
                message=str(e),
                recoverable=recoverable,
                retry_after_seconds=60 if recoverable else None
            )
    
    async def validate_connection(self) -> bool:
        """Validate Gemini API connection."""
        try:
            # Simple test - create agent and validate
            agent = Agent(model=self.model)
            result = await agent.run("Say 'test' only.")
            return True
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """Get model information."""
        return {
            "provider": "google",
            "model_name": self.model_name,
            "api_type": "generative_language_api",  # Using API key, not VertexAI
            "capabilities": ["document_understanding", "structured_output"],
            "supports_document_url": True
        }
    
    def _default_system_prompt(self) -> str:
        """Default system prompt for document extraction."""
        return """You are an expert document extraction AI.

Your task is to extract structured data from financial/loan documents with high accuracy.

Rules:
1. Extract only data explicitly present in the document
2. Do not hallucinate or generate missing information
3. Return empty/missing fields if data is not found
4. Provide confidence in your extraction
5. Note the source location (page number) for each field

Use the provided schema strictly. Validate all extracted data against field types and constraints.
"""
```

## Deliverables
- [ ] adapters/local_storage.py with LocalFileSystemAdapter
- [ ] adapters/memory_queue.py with AsyncMemoryQueueAdapter
- [ ] adapters/sqlite_db.py with SQLiteAdapter
- [ ] adapters/gemini_llm.py with GeminiAdapter
- [ ] All adapters implement their respective ports
- [ ] Error handling with appropriate logging
- [ ] Async/await patterns throughout

## Success Criteria
- All adapters pass mypy type checking
- Local storage can upload/download/delete files
- Memory queue can publish/subscribe to messages
- SQLite adapter can CRUD records
- Gemini adapter can extract structured data from documents

## Testing Snippet
```python
# Test script for adapters
async def test_adapters():
    # Storage
    storage = LocalFileSystemAdapter("./test_uploads")
    # ... upload test
    
    # Queue
    queue = AsyncMemoryQueueAdapter()
    # ... publish/subscribe test
    
    # Database
    db = SQLiteAdapter("sqlite:///./test.db")
    # ... CRUD test
    
    # LLM (requires API key)
    llm = GeminiAdapter()
    # ... extraction test
```

## Next Prompt
After this completes, move to `06_adapters_production.md` for production scaffolding.
