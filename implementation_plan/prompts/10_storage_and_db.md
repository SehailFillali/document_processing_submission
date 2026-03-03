# Prompt 10: Storage and Database - Persistence Layer

## Status
[POSTPONED] - SQLAlchemy ORM skipped, SQLiteAdapter with JSON used instead

## Context
Implementing the persistence layer for submissions and extraction results using SQLite for MVP.

## Objective
Create database models and repository pattern for persisting submission and extraction data.

## Requirements

### 1. Create SQLAlchemy Models (Alternative to raw SQLite)
File: `src/doc_extract/adapters/sqlalchemy_models.py`

```python
"""SQLAlchemy models for database persistence.

Provides ORM layer on top of SQLite for MVP.
Can be swapped to PostgreSQL in production by changing DATABASE_URL.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, 
    DateTime, JSON, ForeignKey, Text, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()


class SubmissionModel(Base):
    """Database model for document submissions."""
    
    __tablename__ = "submissions"
    
    id = Column(String(36), primary_key=True)
    status = Column(String(20), nullable=False, default="pending")
    borrower_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    processing_metadata = Column(JSON, default=dict)
    
    # Relationships
    documents = relationship("DocumentModel", back_populates="submission", cascade="all, delete-orphan")
    extraction_result = relationship("ExtractionResultModel", back_populates="submission", uselist=False)


class DocumentModel(Base):
    """Database model for uploaded documents."""
    
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for idempotency
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    page_count = Column(Integer, nullable=True)
    document_type = Column(String(50), nullable=True)
    storage_path = Column(String(500), nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    submission = relationship("SubmissionModel", back_populates="documents")


class ExtractionResultModel(Base):
    """Database model for extraction results."""
    
    __tablename__ = "extraction_results"
    
    id = Column(String(36), primary_key=True)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False, unique=True)
    status = Column(String(20), nullable=False)
    
    # Borrower profile JSON
    borrower_profile = Column(JSON, nullable=True)
    
    # Metadata
    extraction_confidence = Column(Float, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    token_usage = Column(JSON, nullable=True)
    validation_errors = Column(JSON, default=list)
    requires_manual_review = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    submission = relationship("SubmissionModel", back_populates="extraction_result")


# Database engine and session
engine = None
SessionLocal = None


def init_db(database_url: str = "sqlite:///./data/extraction.db"):
    """Initialize database connection."""
    global engine, SessionLocal
    
    engine = create_engine(
        database_url,
        echo=False,  # Set True for SQL logging
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    return engine


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 2. Create Repository Pattern
File: `src/doc_extract/adapters/repository.py`

```python
"""Repository pattern for data access.

Provides clean abstraction over database operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from doc_extract.adapters.sqlalchemy_models import (
    SubmissionModel, DocumentModel, ExtractionResultModel, get_db
)
from doc_extract.domain.submission import DocumentSubmission, DocumentMetadata, SubmissionStatus
from doc_extract.domain.borrower import ExtractionResult


class SubmissionRepository:
    """Repository for submission operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, submission: DocumentSubmission) -> str:
        """Create new submission."""
        # Convert domain model to ORM
        orm_submission = SubmissionModel(
            id=submission.submission_id,
            status=submission.status.value,
            borrower_id=submission.borrower_profile_id,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
            completed_at=submission.completed_at,
            error_message=submission.error_message,
            processing_metadata=submission.processing_metadata
        )
        
        # Add documents
        for doc in submission.documents:
            orm_doc = DocumentModel(
                id=doc.document_id,
                file_hash=doc.file_hash,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                page_count=doc.page_count,
                document_type=doc.document_type.value if doc.document_type else None,
                storage_path=f"{submission.submission_id}/{doc.file_name}",
                upload_timestamp=doc.upload_timestamp
            )
            orm_submission.documents.append(orm_doc)
        
        self.db.add(orm_submission)
        self.db.commit()
        
        return submission.submission_id
    
    def get_by_id(self, submission_id: str) -> Optional[DocumentSubmission]:
        """Get submission by ID."""
        orm_sub = self.db.query(SubmissionModel).filter(
            SubmissionModel.id == submission_id
        ).first()
        
        if not orm_sub:
            return None
        
        return self._to_domain(orm_sub)
    
    def get_by_file_hash(self, file_hash: str) -> Optional[str]:
        """Get submission ID by file hash (for idempotency)."""
        doc = self.db.query(DocumentModel).filter(
            DocumentModel.file_hash == file_hash
        ).first()
        
        if doc:
            return doc.submission_id
        return None
    
    def update_status(
        self, 
        submission_id: str, 
        status: SubmissionStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """Update submission status."""
        orm_sub = self.db.query(SubmissionModel).filter(
            SubmissionModel.id == submission_id
        ).first()
        
        if not orm_sub:
            return False
        
        orm_sub.status = status.value
        orm_sub.error_message = error_message
        
        if status in [SubmissionStatus.COMPLETED, SubmissionStatus.FAILED]:
            from datetime import datetime
            orm_sub.completed_at = datetime.utcnow()
        
        self.db.commit()
        return True
    
    def _to_domain(self, orm_sub: SubmissionModel) -> DocumentSubmission:
        """Convert ORM to domain model."""
        return DocumentSubmission(
            submission_id=orm_sub.id,
            status=SubmissionStatus(orm_sub.status),
            documents=[
                DocumentMetadata(
                    document_id=d.id,
                    file_hash=d.file_hash,
                    file_name=d.file_name,
                    file_size=d.file_size,
                    mime_type=d.mime_type,
                    page_count=d.page_count,
                    upload_timestamp=d.upload_timestamp
                )
                for d in orm_sub.documents
            ],
            borrower_profile_id=orm_sub.borrower_id,
            created_at=orm_sub.created_at,
            updated_at=orm_sub.updated_at,
            completed_at=orm_sub.completed_at,
            error_message=orm_sub.error_message,
            processing_metadata=orm_sub.processing_metadata or {}
        )


class ExtractionResultRepository:
    """Repository for extraction results."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save(self, result: ExtractionResult) -> str:
        """Save extraction result."""
        orm_result = ExtractionResultModel(
            id=result.submission_id,
            submission_id=result.submission_id,
            status=result.status,
            borrower_profile=result.borrower_profile.model_dump() if result.borrower_profile else None,
            extraction_confidence=result.borrower_profile.extraction_confidence if result.borrower_profile else None,
            processing_time_seconds=result.processing_time_seconds,
            token_usage=result.token_usage,
            validation_errors=result.errors,
            requires_manual_review=result.borrower_profile.requires_manual_review if result.borrower_profile else False
        )
        
        self.db.add(orm_result)
        self.db.commit()
        
        return result.submission_id
    
    def get_by_submission_id(self, submission_id: str) -> Optional[ExtractionResult]:
        """Get extraction result by submission ID."""
        orm_result = self.db.query(ExtractionResultModel).filter(
            ExtractionResultModel.submission_id == submission_id
        ).first()
        
        if not orm_result:
            return None
        
        return self._to_domain(orm_result)
    
    def _to_domain(self, orm_result: ExtractionResultModel) -> ExtractionResult:
        """Convert ORM to domain model."""
        from doc_extract.domain.borrower import BorrowerProfile
        
        borrower_profile = None
        if orm_result.borrower_profile:
            borrower_profile = BorrowerProfile(**orm_result.borrower_profile)
        
        return ExtractionResult(
            submission_id=orm_result.submission_id,
            status=orm_result.status,
            borrower_profile=borrower_profile,
            errors=orm_result.validation_errors or [],
            processing_time_seconds=orm_result.processing_time_seconds,
            token_usage=orm_result.token_usage
        )
```

### 3. Create Database Initialization
File: `src/doc_extract/adapters/database_init.py`

```python
"""Database initialization and connection management."""
import os
from contextlib import contextmanager

from doc_extract.adapters.sqlalchemy_models import init_db, get_db, engine
from doc_extract.core.config import settings
from doc_extract.core.logging import logger


def setup_database():
    """Initialize database on application startup."""
    try:
        # Ensure data directory exists
        db_path = settings.database_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize database
        init_db(settings.database_url)
        
        logger.info(f"Database initialized at {settings.database_url}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@contextmanager
def get_repository_session():
    """Context manager for repository sessions."""
    from doc_extract.adapters.repository import SubmissionRepository, ExtractionResultRepository
    
    db = next(get_db())
    try:
        yield {
            "submissions": SubmissionRepository(db),
            "extractions": ExtractionResultRepository(db)
        }
    finally:
        db.close()
```

## Deliverables
- [ ] adapters/sqlalchemy_models.py with Submission, Document, ExtractionResult models
- [ ] adapters/repository.py with SubmissionRepository and ExtractionResultRepository
- [ ] adapters/database_init.py with setup function
- [ ] SQLAlchemy ORM layer over SQLite
- [ ] Proper relationships and indexes (file_hash indexed for idempotency)

## Success Criteria
- Database tables created on startup
- Submissions can be created and retrieved
- File hash index enables fast idempotency checks
- Repository pattern provides clean data access
- Extraction results persist with full BorrowerProfile JSON

## Testing Snippets
```python
# Test database operations
from doc_extract.adapters.database_init import setup_database
from doc_extract.adapters.repository import SubmissionRepository
from sqlalchemy.orm import Session

setup_database()

# Create submission
repo = SubmissionRepository(db_session)
submission_id = repo.create(test_submission)

# Check idempotency
existing = repo.get_by_file_hash(test_hash)
assert existing == submission_id
```

## Next Prompt
After this completes, move to `11_tests_and_eval.md` for evaluation framework.
