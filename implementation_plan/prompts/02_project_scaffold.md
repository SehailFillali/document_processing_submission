# Prompt 02: Project Scaffold - Docker and Basic Structure

## Status
[COMPLETED]

## Context
Building on the project setup, we now need containerization and the basic Python package structure.

## Objective
Create Docker setup, core module structure, and configuration management.

## Requirements

### 1. Create Multi-Stage Dockerfile
Based on the Clearco llm-service scaffold, adapt for this project:

```dockerfile
# syntax = docker/dockerfile:1.9

FROM python:3.11-slim-bookworm AS build

SHELL ["/bin/sh", "-exc"]

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

ARG PORT=8000
EXPOSE ${PORT}

# Create non-root user
RUN <<EOT
    groupadd -g 999 doc_extract
    useradd -r -d /app -u 999 -g doc_extract doc_extract
EOT

STOPSIGNAL SIGINT

# Copy dependency files
COPY README.md /app
COPY pyproject.toml /app
COPY uv.lock /app

# Copy source code
COPY src/doc_extract /app/src/doc_extract
WORKDIR /app

# Install dependencies
RUN uv sync --frozen --no-cache

# Switch to non-root user
USER doc_extract

# Run the application
CMD ["uv", "run", "-m", "doc_extract.api.main"]
```

### 2. Create docker-compose.yml
For local development with optional services:

```yaml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - ENVIRONMENT=local
      - DATABASE_URL=sqlite:///./data/extraction.db
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    command: uv run uvicorn doc_extract.api.main:app --host 0.0.0.0 --port 8000 --reload
    
  # Optional: PostgreSQL for production-like testing
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: doc_extract
      POSTGRES_PASSWORD: doc_extract
      POSTGRES_DB: extraction
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # Only start if explicitly enabled
    profiles:
      - postgres

volumes:
  postgres_data:
```

### 3. Create Core Configuration Module
File: `src/doc_extract/core/config.py`

```python
"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Provider
    gemini_api_key: str = Field(..., description="Gemini API key from Google AI Studio")
    
    # App Config
    environment: str = Field(default="local", description="Environment: local, dev, staging, production")
    log_level: str = Field(default="INFO", description="Logging level")
    server_ip: str = Field(default="0.0.0.0", description="Server bind IP")
    server_port: int = Field(default=8000, description="Server port")
    
    # Database
    database_url: str = Field(default="sqlite:///./data/extraction.db", description="Database connection URL")
    
    # Optional: GCP
    google_cloud_project: str | None = Field(default=None, description="GCP project ID")
    gcs_bucket_name: str | None = Field(default=None, description="GCS bucket for uploads")
    
    # Processing
    max_file_size_mb: int = Field(default=50, description="Maximum file upload size in MB")
    allowed_extensions: list[str] = Field(default=[".pdf", ".json"], description="Allowed file extensions")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
```

### 4. Create Logging Configuration
File: `src/doc_extract/core/logging.py`

```python
"""Structured logging configuration with loguru."""
import sys
from loguru import logger
from doc_extract.core.config import settings


def setup_logging(log_level: str | None = None) -> None:
    """Configure structured JSON logging.
    
    Args:
        log_level: Optional override for log level
    """
    level = log_level or settings.log_level
    
    # Remove default handler
    logger.remove()
    
    # Add console handler with JSON formatting for production
    if settings.environment == "production":
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
            level=level,
            serialize=True,  # JSON format
        )
    else:
        # Pretty format for local development
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
            level=level,
            colorize=True,
        )
    
    # Add file handler
    logger.add(
        "logs/app.log",
        rotation="10 MB",
        retention="1 week",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
        level=level,
        enqueue=True,
    )


# Export configured logger
__all__ = ["logger", "setup_logging"]
```

### 5. Create Exceptions Module
File: `src/doc_extract/core/exceptions.py`

```python
"""Custom exceptions with error codes for the document extraction system."""


class DocExtractError(Exception):
    """Base exception for all document extraction errors."""
    
    def __init__(self, message: str, error_code: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class ValidationError(DocExtractError):
    """Raised when document validation fails."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, "VALIDATION_ERROR", details)


class ProcessingError(DocExtractError):
    """Raised when document processing fails."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, "PROCESSING_ERROR", details)


class StorageError(DocExtractError):
    """Raised when storage operations fail."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, "STORAGE_ERROR", details)


class LLMError(DocExtractError):
    """Raised when LLM extraction fails."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, "LLM_ERROR", details)
```

### 6. Create __init__.py files
Create empty `__init__.py` in:
- `src/doc_extract/__init__.py`
- `src/doc_extract/api/__init__.py`
- `src/doc_extract/core/__init__.py`
- `src/doc_extract/domain/__init__.py`
- `src/doc_extract/ports/__init__.py`
- `src/doc_extract/adapters/__init__.py`
- `src/doc_extract/services/__init__.py`
- `src/doc_extract/utils/__init__.py`

## Deliverables
- [ ] Multi-stage Dockerfile created
- [ ] docker-compose.yml with optional postgres
- [ ] core/config.py with pydantic-settings
- [ ] core/logging.py with loguru
- [ ] core/exceptions.py with custom exceptions
- [ ] All __init__.py files created
- [ ] Test Docker build with `docker build -t doc-extract:test .`

## Success Criteria
- Docker build completes without errors
- `docker-compose up` starts the API service
- Settings load from .env file
- Logger outputs structured JSON in production mode

## Code Snippets to Include
All files above are complete, ready to copy-paste.

## Next Prompt
After this completes, move to `03_domain_models.md` for Pydantic models.
