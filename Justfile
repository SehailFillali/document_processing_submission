# Variables
export PYTHONPATH := "src"
export ENVIRONMENT := env_var_or_default("ENVIRONMENT", "local")

# Setup - install dependencies
setup:
	@echo "Setting up project with uv..."
	uv sync --all-groups
	@echo "Setup complete!"

# Development server
dev:
	uv run uvicorn doc_extract.api.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	uv run pytest tests/ -v --cov=src/doc_extract --cov-report=term-missing

# Run linting
lint:
	uv run ruff check src/ tests/
	uv run mypy src/

# Format code
format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

# Build Docker image
build-image:
	docker build -t doc-extract:latest .

# Run with Docker Compose
dev-docker:
	docker-compose up -d --build

# Run evaluation script (to be implemented)
evaluate:
	uv run python -m tests.evaluation.run_eval

# Clean build artifacts
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Reset database and uploads (fresh start for demo)
reset:
	@echo "Stopping API container..."
	docker compose down 2>/dev/null || true
	@echo "Clearing database and uploads..."
	rm -f data/extraction.db
	docker run --rm -v "$(pwd)/uploads:/uploads" alpine sh -c "rm -rf /uploads/*" 2>/dev/null || rm -rf uploads/* 2>/dev/null || true
	mkdir -p data uploads
	@echo "Done. Run 'just dev-docker' to start fresh."

# Full CI pipeline (lint + test)
ci: lint test
	@echo "CI pipeline complete!"

# Default recipe
default:
	@just --list
