# syntax = docker/dockerfile:1.9

FROM python:3.11-slim-bookworm AS build

SHELL ["/bin/sh", "-exc"]

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_NO_CACHE=1

ARG PORT=8000
EXPOSE ${PORT}

# Create non-root user and app directory
RUN <<EOT
    mkdir -p /app/data /app/uploads /app/logs
    chmod 777 /app/data /app/uploads /app/logs
    groupadd -g 999 doc_extract
    useradd -r -d /app -u 999 -g doc_extract doc_extract
EOT

STOPSIGNAL SIGINT

WORKDIR /app

# Copy dependency files
COPY README.md pyproject.toml uv.lock ./

# Copy source code
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-cache

# Switch to non-root user
USER doc_extract

# Run the application
CMD ["uv", "run", "-m", "doc_extract.api.main"]
