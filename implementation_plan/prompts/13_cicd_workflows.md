# Prompt 13: CI/CD Workflows - GitHub Actions

## Status
[PARTIALLY_IMPLEMENTED] - missing terraform.yml workflow

## Context
Creating GitHub Actions workflows for continuous integration and deployment to Cloud Run.

## Objective
Implement CI/CD pipelines for lint, test, build, and deploy using gcloud CLI.

## Requirements

### 1. Create CI Workflow (Lint, Test, Build)
File: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.cargo/bin" >> $GITHUB_PATH
      
      - name: Install dependencies
        run: uv sync --all-groups
      
      - name: Run linting
        run: |
          uv run ruff check src/ tests/
          uv run mypy src/
      
      - name: Run tests
        run: uv run pytest tests/ -v --cov=src/doc_extract --cov-report=xml
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          fail_ci_if_error: false

  build-image:
    runs-on: ubuntu-latest
    needs: lint-and-test
    if: github.event_name == 'push'
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      
      - name: Configure Docker for GCR
        run: gcloud auth configure-docker gcr.io
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:${{ github.sha }}
            gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 2. Create Deploy Workflow (Cloud Run)
File: `.github/workflows/deploy.yml`

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy to'
        required: true
        default: 'dev'
        type: choice
        options:
          - dev
          - staging
          - production

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment || 'dev' }}
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
          project_id: ${{ secrets.GCP_PROJECT_ID }}
      
      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
      
      - name: Configure Docker for GCR
        run: gcloud auth configure-docker gcr.io
      
      - name: Build Docker image
        run: |
          docker build \
            -t gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:${{ github.sha }} \
            -t gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:latest \
            .
      
      - name: Push Docker image
        run: |
          docker push gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:${{ github.sha }}
          docker push gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:latest
      
      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy doc-extract \
            --image gcr.io/${{ secrets.GCP_PROJECT_ID }}/doc-extract:${{ github.sha }} \
            --region us-central1 \
            --platform managed \
            --allow-unauthenticated \
            --set-env-vars "ENVIRONMENT=${{ inputs.environment || 'dev' }}" \
            --set-env-vars "LOG_LEVEL=INFO" \
            --set-secrets "GEMINI_API_KEY=gemini-api-key:latest" \
            --min-instances=1 \
            --max-instances=20 \
            --cpu=2 \
            --memory=4Gi \
            --port=8000 \
            --service-account=doc-extract-runtime@${{ secrets.GCP_PROJECT_ID }}.iam.gserviceaccount.com
      
      - name: Verify deployment
        run: |
          URL=$(gcloud run services describe doc-extract --region=us-central1 --format='value(status.url)')
          echo "Deployed to: $URL"
          
          # Health check
          curl -f "$URL/health" || exit 1
      
      - name: Notify deployment
        if: always()
        run: |
          echo "Deployment to ${{ inputs.environment || 'dev' }} ${{ job.status }}"
```

### 3. Create Evaluation Workflow
File: `.github/workflows/evaluate.yml`

```yaml
name: Evaluation

on:
  schedule:
    - cron: '0 2 * * 1'  # Run weekly on Mondays at 2 AM
  workflow_dispatch:

jobs:
  evaluation:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.cargo/bin" >> $GITHUB_PATH
      
      - name: Install dependencies
        run: uv sync --all-groups
      
      - name: Run evaluation
        run: uv run python -m tests.evaluation.run_eval
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-results
          path: tests/evaluation/results/
      
      - name: Check F1 threshold
        run: |
          # Extract F1 score from results and check threshold
          # Exit with error if below 0.8
          echo "F1 threshold check would go here"
```

### 4. Create Terraform Validation Workflow
File: `.github/workflows/terraform.yml`

```yaml
name: Terraform

on:
  push:
    paths:
      - 'infra/**'
  pull_request:
    paths:
      - 'infra/**'

jobs:
  terraform:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.7.0"
      
      - name: Terraform Format
        run: terraform fmt -check -recursive
        working-directory: infra
      
      - name: Terraform Init
        run: terraform init -backend=false
        working-directory: infra
      
      - name: Terraform Validate
        run: terraform validate
        working-directory: infra
      
      - name: Terraform Plan
        run: terraform plan -var="project_id=dummy-project" -var="region=us-central1"
        working-directory: infra
        env:
          GOOGLE_CREDENTIALS: '{"type":"service_account"}'  # Dummy for validation
```

## Deliverables
- [ ] .github/workflows/ci.yml for lint/test/build
- [ ] .github/workflows/deploy.yml for Cloud Run deployment
- [ ] .github/workflows/evaluate.yml for weekly evaluation
- [ ] .github/workflows/terraform.yml for IaC validation
- [ ] All workflows use GEMINI_API_KEY from secrets
- [ ] GCP authentication via service account key
- [ ] Deployment uses gcloud CLI commands

## Success Criteria
- CI runs on every PR (lint + test)
- Docker image builds and pushes to GCR on main branch
- Deploy workflow updates Cloud Run with new image
- Evaluation runs weekly and checks F1 threshold
- Terraform files validated on every change
- Secrets required documented:
  - GEMINI_API_KEY
  - GCP_SA_KEY (service account JSON)
  - GCP_PROJECT_ID

## Required GitHub Secrets
Add these to repository Settings > Secrets:

1. **GEMINI_API_KEY** - From Google AI Studio (https://aistudio.google.com/app/apikey)
2. **GCP_SA_KEY** - Service account JSON key with roles:
   - Cloud Run Admin
   - Storage Admin
   - Artifact Registry Reader
3. **GCP_PROJECT_ID** - Your GCP project ID

## Next Prompt
After this completes, move to `14_adrs.md` for Architecture Decision Records.
