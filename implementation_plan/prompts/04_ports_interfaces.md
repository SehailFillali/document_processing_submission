# Prompt 04: Ports and Interfaces - Hexagonal Architecture

## Status
[COMPLETED]

## Context
Implementing Hexagonal Architecture (Ports & Adapters) to decouple core logic from infrastructure. This enables testing and future extensibility.

## Objective
Define protocol interfaces (ports) for storage, queue, and LLM operations.

## Requirements

### 1. Create Storage Port (Blob Storage)
File: `src/doc_extract/ports/storage.py`

```python
"""Storage port - abstraction for blob storage operations."""
from abc import ABC, abstractmethod
from typing import BinaryIO
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StorageMetadata:
    """Metadata about a stored file."""
    path: str
    size: int
    content_type: str
    created_at: datetime
    checksum: str | None = None


class BlobStoragePort(ABC):
    """Port for blob storage operations.
    
    This abstract base class defines the contract for all storage implementations.
    It follows the Port & Adapter pattern from Hexagonal Architecture.
    
    Implementations:
        - LocalFileSystemAdapter: For local development
        - GCSStorageAdapter: For production (Google Cloud Storage)
    """
    
    @abstractmethod
    async def upload(
        self, 
        file_data: BinaryIO, 
        destination_path: str,
        content_type: str | None = None
    ) -> StorageMetadata:
        """Upload a file to storage.
        
        Args:
            file_data: Binary stream of the file
            destination_path: Path where file should be stored
            content_type: MIME type of the file
            
        Returns:
            StorageMetadata with file details
        """
        pass
    
    @abstractmethod
    async def download(self, source_path: str) -> bytes:
        """Download a file from storage.
        
        Args:
            source_path: Path to the file
            
        Returns:
            File content as bytes
        """
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file from storage.
        
        Args:
            path: Path to the file
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists.
        
        Args:
            path: Path to check
            
        Returns:
            True if file exists
        """
        pass
    
    @abstractmethod
    async def generate_signed_url(
        self, 
        path: str, 
        expiration_seconds: int = 3600
    ) -> str:
        """Generate a signed URL for temporary access.
        
        Args:
            path: Path to the file
            expiration_seconds: URL validity duration
            
        Returns:
            Signed URL string
        """
        pass
    
    @abstractmethod
    async def get_metadata(self, path: str) -> StorageMetadata | None:
        """Get metadata for a file.
        
        Args:
            path: Path to the file
            
        Returns:
            StorageMetadata or None if not found
        """
        pass
```

### 2. Create Queue Port (Message Queue)
File: `src/doc_extract/ports/queue.py`

```python
"""Queue port - abstraction for message queue operations."""
from abc import ABC, abstractmethod
from typing import Callable, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio


@dataclass
class QueueMessage:
    """A message in the queue."""
    message_id: str
    body: dict
    timestamp: datetime
    attempts: int = 0
    metadata: dict | None = None


@dataclass
class QueueSubscription:
    """Subscription handle for cleanup."""
    subscription_id: str
    
    async def unsubscribe(self) -> None:
        """Unsubscribe from the queue."""
        pass


class QueuePort(ABC):
    """Port for message queue operations.
    
    This enables decoupled, event-driven architecture.
    
    Implementations:
        - AsyncMemoryQueueAdapter: In-memory queue for local dev
        - GooglePubSubAdapter: Google Pub/Sub for production
    """
    
    @abstractmethod
    async def publish(self, topic: str, message: dict) -> str:
        """Publish a message to a topic.
        
        Args:
            topic: Topic/channel name
            message: Message payload (must be JSON-serializable)
            
        Returns:
            Message ID
        """
        pass
    
    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[QueueMessage], Any],
        **kwargs
    ) -> QueueSubscription:
        """Subscribe to a topic.
        
        Args:
            topic: Topic to subscribe to
            handler: Callback function for messages
            **kwargs: Implementation-specific options
            
        Returns:
            Subscription handle
        """
        pass
    
    @abstractmethod
    async def acknowledge(self, message_id: str) -> bool:
        """Acknowledge successful message processing.
        
        Args:
            message_id: ID of the message to ack
            
        Returns:
            True if acknowledged
        """
        pass
    
    @abstractmethod
    async def reject(
        self, 
        message_id: str, 
        requeue: bool = False,
        reason: str | None = None
    ) -> bool:
        """Reject a message (negative acknowledge).
        
        Args:
            message_id: ID of the message
            requeue: Whether to requeue for retry
            reason: Rejection reason for logging
            
        Returns:
            True if rejected
        """
        pass
    
    @abstractmethod
    async def publish_to_dlq(
        self, 
        message: QueueMessage, 
        reason: str
    ) -> str:
        """Publish message to Dead Letter Queue after max retries.
        
        Args:
            message: The failed message
            reason: Why it failed
            
        Returns:
            DLQ message ID
        """
        pass
```

### 3. Create LLM Port (AI/Extraction)
File: `src/doc_extract/ports/llm.py`

```python
"""LLM port - abstraction for AI model operations."""
from abc import ABC, abstractmethod
from typing import TypeVar, Type
from dataclasses import dataclass
from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


@dataclass
class ExtractionRequest:
    """Request for LLM extraction."""
    document_url: str  # Can be gs://, file://, or https://
    document_type: str
    output_schema: Type[BaseModel]
    system_prompt: str | None = None
    validation_rules: list | None = None


@dataclass
class ExtractionResponse:
    """Response from LLM extraction."""
    extracted_data: BaseModel
    raw_output: str | None = None
    token_usage: dict
    confidence_score: float
    processing_time_seconds: float
    model_name: str


@dataclass
class LLMError:
    """Structured LLM error."""
    error_type: str
    message: str
    recoverable: bool
    retry_after_seconds: int | None = None


class LLMPort(ABC):
    """Port for LLM operations.
    
    This abstracts away the specific LLM provider (Gemini, OpenAI, etc.)
    and provides a unified interface for document extraction.
    
    Implementations:
        - GeminiAdapter: Google Gemini via API key
        - OpenAIAdapter: OpenAI GPT models
        - VertexAIAdapter: Google Vertex AI (service account)
    """
    
    @abstractmethod
    async def extract_structured(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data from a document.
        
        Args:
            request: Extraction request with document URL and schema
            
        Returns:
            ExtractionResponse with validated data
            
        Raises:
            LLMError: If extraction fails
        """
        pass
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate that LLM service is accessible.
        
        Returns:
            True if connection is valid
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> dict:
        """Get information about the configured model.
        
        Returns:
            Dict with model name, version, capabilities
        """
        pass
```

### 4. Create Database Port
File: `src/doc_extract/ports/database.py`

```python
"""Database port - abstraction for persistence operations."""
from abc import ABC, abstractmethod
from typing import TypeVar, Type, Any
from dataclasses import dataclass


T = TypeVar("T")


@dataclass
class QueryFilter:
    """Filter for database queries."""
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, in, contains
    value: Any


@dataclass
class QueryResult:
    """Result of a database query."""
    items: list[Any]
    total_count: int
    page: int
    page_size: int


class DatabasePort(ABC):
    """Port for database operations.
    
    This abstracts the specific database (SQLite, PostgreSQL, etc.)
    and provides a unified interface for persistence.
    
    Implementations:
        - SQLiteAdapter: SQLite for MVP/local dev
        - PostgreSQLAdapter: Postgres for production
    """
    
    @abstractmethod
    async def create(self, table: str, data: dict) -> str:
        """Create a new record.
        
        Args:
            table: Table/collection name
            data: Record data
            
        Returns:
            Record ID
        """
        pass
    
    @abstractmethod
    async def read(
        self, 
        table: str, 
        record_id: str
    ) -> dict | None:
        """Read a record by ID.
        
        Args:
            table: Table/collection name
            record_id: Record ID
            
        Returns:
            Record data or None
        """
        pass
    
    @abstractmethod
    async def update(
        self, 
        table: str, 
        record_id: str, 
        data: dict
    ) -> bool:
        """Update a record.
        
        Args:
            table: Table/collection name
            record_id: Record ID
            data: Fields to update
            
        Returns:
            True if updated
        """
        pass
    
    @abstractmethod
    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record.
        
        Args:
            table: Table/collection name
            record_id: Record ID
            
        Returns:
            True if deleted
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        table: str,
        filters: list[QueryFilter] | None = None,
        order_by: str | None = None,
        page: int = 1,
        page_size: int = 20
    ) -> QueryResult:
        """Query records with filters.
        
        Args:
            table: Table/collection name
            filters: Optional list of filters
            order_by: Field to order by
            page: Page number (1-indexed)
            page_size: Items per page
            
        Returns:
            QueryResult with items and metadata
        """
        pass
    
    @abstractmethod
    async def upsert(
        self, 
        table: str, 
        record_id: str, 
        data: dict
    ) -> str:
        """Insert or update a record (idempotent).
        
        Args:
            table: Table/collection name
            record_id: Record ID (often a hash for idempotency)
            data: Record data
            
        Returns:
            Record ID
        """
        pass
```

## Deliverables
- [ ] ports/storage.py with BlobStoragePort and StorageMetadata
- [ ] ports/queue.py with QueuePort, QueueMessage, QueueSubscription
- [ ] ports/llm.py with LLMPort, ExtractionRequest, ExtractionResponse
- [ ] ports/database.py with DatabasePort, QueryFilter, QueryResult
- [ ] All ports are abstract base classes (ABC) with @abstractmethod
- [ ] Comprehensive docstrings explaining the Port & Adapter pattern

## Success Criteria
- All ports define clear, consistent interfaces
- No infrastructure-specific code in ports (pure abstractions)
- Return types are well-defined dataclasses or Pydantic models
- Error handling patterns established

## Documentation Note
Include comments in each file explaining:
- Why Hexagonal Architecture: Decouples business logic from infrastructure
- Benefits: Testability (mock adapters), Swapability (change providers), Single Responsibility
- How it works: Core uses Ports (interfaces), Adapters implement Ports

## Next Prompt
After this completes, move to `05_adapters_local.md` for local implementations.
