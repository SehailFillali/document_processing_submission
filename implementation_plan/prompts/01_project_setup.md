# Prompt 01: Project Setup - Dependencies and Tooling

## Status
[COMPLETED]

## Context
We need to establish the foundation of our document extraction system using the modern Python stack from the blueprint.

## Objective
Create the project scaffolding with `uv`, `just`, and all baseline dependencies.

## Requirements

### 1. Initialize Project Structure
Create the following folder structure:
```
document-extraction-system/
├── src/
│   └── doc_extract/
│       ├── __init__.py
│       ├── api/
│       ├── core/
│       ├── domain/
│       ├── ports/
│       ├── adapters/
│       ├── services/
│       └── utils/
├── tests/
│   ├── integration/
│   └── evaluation/
├── infra/
├── docs/
│   └── adr/
├── .github/
│   └── workflows/
├── data/
└── uploads/
```

### 2. Create pyproject.toml
Use these exact dependencies:

```toml
[project]
name = "doc-extract"
version = "0.1.0"
description = "Document extraction system using PydanticAI and Gemini"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.8.0",
    "pydantic-ai>=0.0.20",
    "pydantic-graph>=0.0.20",
    "loguru>=0.7.3",
    "stamina>=24.3.0",
    "python-multipart>=0.0.20",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.21.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "hypothesis>=6.122.0",
    "ruff>=0.9.0",
    "mypy>=1.14.0",
    "httpx>=0.28.0",
]

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"
editable = true

[tool.ruff]
target-version = "py311"
line-length = 88
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["src"]
```

### 3. Create Justfile
Replace the Makefile with a modern Justfile:

```justfile
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
    docker-compose up --build

# Run evaluation script (to be implemented)
evaluate:
    uv run python -m tests.evaluation.run_eval

# Clean up
clean:
    rm -rf .pytest_cache .ruff_cache .mypy_cache
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Full CI pipeline (lint + test)
ci: lint test
    @echo "CI pipeline complete!"

# Default recipe
default:
    @just --list
```

### 4. Create .env.example

```bash
# LLM Provider - Gemini API Key (get from https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# App Configuration
LOG_LEVEL=INFO
ENVIRONMENT=local
SERVER_IP=0.0.0.0
SERVER_PORT=8000

# Database (SQLite for MVP)
DATABASE_URL=sqlite:///./data/extraction.db

# Optional: GCP settings for production features
GOOGLE_CLOUD_PROJECT=
GCS_BUCKET_NAME=
```

### 5. Create .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
*.egg-info/
dist/
build/

# UV
uv.lock

# Environment
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# Data
data/*.db
data/*.sqlite
uploads/*.pdf
uploads/*.json

# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl

# OS
.DS_Store
Thumbs.db
```

### 6. Initialize with uv
Run the setup:
```bash
cd document-extraction-system
uv sync --all-groups
```

## Deliverables
- [ ] Folder structure created
- [ ] pyproject.toml with all dependencies
- [ ] Justfile with all commands
- [ ] .env.example with GEMINI_API_KEY
- [ ] .gitignore configured
- [ ] uv sync completed successfully

## Success Criteria
- `just setup` works without errors
- `just --list` shows all available commands
- Virtual environment created and activated
- All dependencies installed

## Code Snippets to Include
Include complete, copy-paste ready versions of all files above.

## Next Prompt
After this completes, move to `02_project_scaffold.md` for Docker and basic structure.
