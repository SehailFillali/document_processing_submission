"""Database port - abstraction for persistence operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class QueryFilter:
    """Filter for database queries."""

    field: str
    operator: str
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
    async def read(self, table: str, record_id: str) -> dict | None:
        """Read a record by ID.

        Args:
            table: Table/collection name
            record_id: Record ID

        Returns:
            Record data or None
        """
        pass

    @abstractmethod
    async def update(self, table: str, record_id: str, data: dict) -> bool:
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
        page_size: int = 20,
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
    async def upsert(self, table: str, record_id: str, data: dict) -> str:
        """Insert or update a record (idempotent).

        Args:
            table: Table/collection name
            record_id: Record ID (often a hash for idempotency)
            data: Record data

        Returns:
            Record ID
        """
        pass
