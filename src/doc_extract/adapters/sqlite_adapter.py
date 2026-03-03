"""SQLite database adapter."""

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from doc_extract.core.config import settings
from doc_extract.core.logging import logger
from doc_extract.ports.database import DatabasePort, QueryFilter, QueryResult


class SQLiteAdapter(DatabasePort):
    """SQLite implementation of DatabasePort."""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or settings.database_url
        self.db_path = self.database_url.replace("sqlite:///", "")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized SQLiteAdapter at {self.db_path}")

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get database connection."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def create(self, table: str, data: dict) -> str:
        """Create a new record."""
        conn = await self._get_connection()
        try:
            data["created_at"] = datetime.now(UTC).isoformat()
            data["updated_at"] = datetime.now(UTC).isoformat()

            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?" for _ in data])

            await conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                list(data.values()),
            )
            await conn.commit()

            record_id = (
                data.get("id")
                or data.get("submission_id")
                or str(datetime.now(UTC).timestamp())
            )
            return record_id

        finally:
            await conn.close()

    async def read(self, table: str, record_id: str) -> dict | None:
        """Read a record by ID."""
        conn = await self._get_connection()
        try:
            # Check if submission_id column exists for this table
            info_cursor = await conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await info_cursor.fetchall()]

            if "submission_id" in columns:
                cursor = await conn.execute(
                    f"SELECT * FROM {table} WHERE id = ? OR submission_id = ?",
                    (record_id, record_id),
                )
            else:
                cursor = await conn.execute(
                    f"SELECT * FROM {table} WHERE id = ?",
                    (record_id,),
                )
            row = await cursor.fetchone()

            if row:
                return dict(row)
            return None

        finally:
            await conn.close()

    async def update(self, table: str, record_id: str, data: dict) -> bool:
        """Update a record."""
        conn = await self._get_connection()
        try:
            data["updated_at"] = datetime.now(UTC).isoformat()

            set_clause = ", ".join([f"{k} = ?" for k in data])

            # Check if submission_id column exists for this table
            info_cursor = await conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await info_cursor.fetchall()]

            if "submission_id" in columns:
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id = ? OR submission_id = ?",
                    list(data.values()) + [record_id, record_id],
                )
            else:
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id = ?",
                    list(data.values()) + [record_id],
                )
            await conn.commit()

            return True

        finally:
            await conn.close()

    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record."""
        conn = await self._get_connection()
        try:
            # Check if submission_id column exists for this table
            info_cursor = await conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await info_cursor.fetchall()]

            if "submission_id" in columns:
                await conn.execute(
                    f"DELETE FROM {table} WHERE id = ? OR submission_id = ?",
                    (record_id, record_id),
                )
            else:
                await conn.execute(
                    f"DELETE FROM {table} WHERE id = ?",
                    (record_id,),
                )
            await conn.commit()
            return True

        finally:
            await conn.close()

    async def query(
        self,
        table: str,
        filters: list[QueryFilter] | None = None,
        order_by: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> QueryResult:
        """Query records with filters."""
        conn = await self._get_connection()
        try:
            query = f"SELECT * FROM {table}"
            params = []

            if filters:
                where_clauses = []
                for f in filters:
                    where_clauses.append(f"{f.field} {f.operator} ?")
                    params.append(f.value)
                query += " WHERE " + " AND ".join(where_clauses)

            if order_by:
                query += f" ORDER BY {order_by}"

            query += f" LIMIT {page_size} OFFSET {(page - 1) * page_size}"

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            total_cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")
            total = await total_cursor.fetchone()

            return QueryResult(
                items=[dict(row) for row in rows],
                total_count=total[0] if total else 0,
                page=page,
                page_size=page_size,
            )

        finally:
            await conn.close()

    async def upsert(self, table: str, record_id: str, data: dict) -> str:
        """Insert or update a record (idempotent)."""
        existing = await self.read(table, record_id)

        if existing:
            await self.update(table, record_id, data)
        else:
            data["id"] = record_id
            await self.create(table, data)

        return record_id

    async def init_tables(self):
        """Initialize database tables."""
        conn = await self._get_connection()
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT UNIQUE,
                    status TEXT,
                    documents TEXT,
                    borrower_profile_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    processing_metadata TEXT
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS borrower_profiles (
                    id TEXT PRIMARY KEY,
                    borrower_id TEXT UNIQUE,
                    data TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            await conn.commit()
            logger.info("Database tables initialized")

        finally:
            await conn.close()
