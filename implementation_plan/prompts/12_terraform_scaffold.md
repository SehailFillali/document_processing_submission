# Prompt 12: Terraform Scaffolding - Infrastructure as Code

## Status
[COMPLETED]

## Context
Creating Terraform scaffolding for production infrastructure without execution.

## Objective
Write Terraform HCL files for Cloud Run, GCS, Pub/Sub, BigQuery, IAM, and Dataform - as documentation and scaffolding only.

## Requirements

### 1. Create Main Terraform File
File: `infra/main.tf`

```hcl
# ==============================================================================
# TERRAFORM SCAFFOLDING - PRODUCTION INFRASTRUCTURE
# ==============================================================================
# 
# This file defines the production infrastructure for the document extraction
# system. It is provided as scaffolding/documentation only - NOT executed in MVP.
#
# To deploy:
#   1. Set up GCP project and billing
#   2. Configure terraform.tfvars with project-specific values
#   3. Run: terraform init && terraform plan && terraform apply
#
# Architecture Decision: See docs/adr/002_storage_strategy.md
# ==============================================================================

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
  
  # Optional: Remote state backend (GCS)
  # backend "gcs" {
  #   bucket = "my-terraform-state-bucket"
  #   prefix = "doc-extract"
  # }
}

# Variables (define in terraform.tfvars or via TF_VAR_* env vars)
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment: dev, staging, production"
  type        = string
  default     = "dev"
}

locals {
  service_name = "doc-extract"
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    service     = local.service_name
  }
}

# ==============================================================================
# SERVICE ACCOUNTS
# ==============================================================================

# Service account for Cloud Run runtime
resource "google_service_account" "doc_extract_runtime" {
  account_id   = "${local.service_name}-runtime"
  display_name = "Document Extraction Service Runtime"
  description  = "Service account for Cloud Run container runtime"
  project      = var.project_id
}

# Service account for Dataform ETL jobs
resource "google_service_account" "doc_extract_etl" {
  account_id   = "${local.service_name}-etl"
  display_name = "Document Extraction ETL Service"
  description  = "Service account for Dataform ETL workflows"
  project      = var.project_id
}

# ==============================================================================
# IAM BINDINGS - RUNTIME SERVICE ACCOUNT
# ==============================================================================

# Storage: Read/write access to GCS buckets
resource "google_project_iam_member" "runtime_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

# Pub/Sub: Publish and subscribe to topics
resource "google_project_iam_member" "runtime_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

resource "google_project_iam_member" "runtime_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

# BigQuery: Write to dataset
resource "google_project_iam_member" "runtime_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

# BigQuery: Run jobs
resource "google_project_iam_member" "runtime_bigquery_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

# Cloud Run: Allow invoking service
resource "google_project_iam_member" "runtime_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.doc_extract_runtime.email}"
}

# ==============================================================================
# IAM BINDINGS - ETL SERVICE ACCOUNT
# ==============================================================================

# Storage: Read from output bucket
resource "google_project_iam_member" "etl_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.doc_extract_etl.email}"
}

# BigQuery: Full access to dataset
resource "google_project_iam_member" "etl_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.doc_extract_etl.email}"
}

# BigQuery: Run jobs
resource "google_project_iam_member" "etl_bigquery_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.doc_extract_etl.email}"
}

# ==============================================================================
# GCS BUCKETS
# ==============================================================================

# Bucket for document uploads
resource "google_storage_bucket" "uploads" {
  name     = "${var.project_id}-${local.service_name}-uploads"
  location = var.region
  project  = var.project_id
  
  # Enable versioning for audit trail
  versioning {
    enabled = true
  }
  
  # Lifecycle: Delete old versions after 30 days
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
      days_since_noncurrent_time = 30
    }
  }
  
  # Encryption with Google-managed key (upgrade to CMEK for production)
  encryption {
    default_kms_key_name = null
  }
  
  labels = local.common_labels
  
  uniform_bucket_level_access = true
}

# Bucket for extraction output (JSON files)
resource "google_storage_bucket" "output" {
  name     = "${var.project_id}-${local.service_name}-output"
  location = var.region
  project  = var.project_id
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age = 30
    }
  }
  
  lifecycle_rule {
    action {
      type = "SetStorageClass"
      storage_class = "COLDLINE"
    }
    condition {
      age = 90
    }
  }
  
  labels = local.common_labels
  uniform_bucket_level_access = true
}

# ==============================================================================
# PUB/SUB TOPICS
# ==============================================================================

# Topic for document upload events
resource "google_pubsub_topic" "document_uploaded" {
  name    = "${local.service_name}-document-uploaded"
  project = var.project_id
  
  labels = local.common_labels
  
  # Message retention for 7 days
  message_retention_duration = "604800s"
}

# Topic for extraction completion events
resource "google_pubsub_topic" "extraction_completed" {
  name    = "${local.service_name}-extraction-completed"
  project = var.project_id
  
  labels = local.common_labels
}

# Dead letter topic for failed messages
resource "google_pubsub_topic" "dlq" {
  name    = "${local.service_name}-dlq"
  project = var.project_id
  
  labels = local.common_labels
}

# ==============================================================================
# BIGQUERY DATASET
# ==============================================================================

resource "google_bigquery_dataset" "extraction" {
  dataset_id  = "${local.service_name}_results"
  project     = var.project_id
  location    = var.region
  description = "Document extraction results dataset"
  
  labels = local.common_labels
  
  # Default expiration for tables (optional)
  default_table_expiration_ms = null
  
  # Access control
  access {
    role          = "OWNER"
    user_by_email = google_service_account.doc_extract_runtime.email
  }
  
  access {
    role          = "WRITER"
    user_by_email = google_service_account.doc_extract_etl.email
  }
}

# Extraction results table
resource "google_bigquery_table" "extraction_results" {
  dataset_id = google_bigquery_dataset.extraction.dataset_id
  project    = var.project_id
  table_id   = "extraction_results"
  
  description = "Structured extraction results from loan documents"
  
  # Partition by date for query performance
  time_partitioning {
    type          = "DAY"
    expiration_ms = null
    field         = "created_at"
  }
  
  # Cluster by submission_id for efficient lookups
  clustering = ["submission_id"]
  
  schema = jsonencode([
    {
      name = "submission_id"
      type = "STRING"
      mode = "REQUIRED"
      description = "Unique submission identifier"
    },
    {
      name = "borrower_profile"
      type = "RECORD"
      mode = "NULLABLE"
      description = "Structured borrower profile"
      fields = [
        {
          name = "name"
          type = "STRING"
          mode = "NULLABLE"
        },
        {
          name = "address"
          type = "RECORD"
          mode = "NULLABLE"
          fields = [
            { name = "street", type = "STRING", mode = "NULLABLE" },
            { name = "city", type = "STRING", mode = "NULLABLE" },
            { name = "state", type = "STRING", mode = "NULLABLE" },
            { name = "zip_code", type = "STRING", mode = "NULLABLE" }
          ]
        },
        {
          name = "income_history"
          type = "RECORD"
          mode = "REPEATED"
          fields = [
            { name = "amount", type = "FLOAT", mode = "NULLABLE" },
            { name = "period_start", type = "DATE", mode = "NULLABLE" },
            { name = "period_end", type = "DATE", mode = "NULLABLE" },
            { name = "source", type = "STRING", mode = "NULLABLE" }
          ]
        }
      ]
    },
    {
      name = "source_documents"
      type = "STRING"
      mode = "REPEATED"
      description = "List of source document URIs"
    },
    {
      name = "extraction_confidence"
      type = "FLOAT"
      mode = "NULLABLE"
      description = "Overall confidence score 0.0-1.0"
    },
    {
      name = "status"
      type = "STRING"
      mode = "REQUIRED"
      description = "extraction status: completed, partial, failed, manual_review"
    },
    {
      name = "created_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Record creation timestamp"
    },
    {
      name = "_loaded_at"
      type = "TIMESTAMP"
      mode = "REQUIRED"
      description = "Data load timestamp for deduplication"
    }
  ])
}

# ==============================================================================
# CLOUD RUN SERVICE
# ==============================================================================

resource "google_cloud_run_v2_service" "doc_extract" {
  name     = local.service_name
  location = var.region
  project  = var.project_id
  
  # Ingress: Allow traffic from anywhere (restrict to VPC for production)
  ingress = "INGRESS_TRAFFIC_ALL"
  
  template {
    # Use runtime service account
    service_account = google_service_account.doc_extract_runtime.email
    
    # Container configuration
    containers {
      # Image configured by CI/CD at deploy time
      # lifecycle_ignore_changes prevents Terraform from overwriting
      image = "gcr.io/${var.project_id}/${local.service_name}:latest"
      
      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle = false
      }
      
      ports {
        container_port = 8000
      }
      
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      
      # Secrets from Secret Manager (configured separately)
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "gemini-api-key"
            version = "latest"
          }
        }
      }
      
      # Health checks
      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 6
        
        http_get {
          path = "/ready"
          port = 8000
        }
      }
      
      liveness_probe {
        timeout_seconds   = 5
        period_seconds    = 10
        failure_threshold = 3
        
        http_get {
          path = "/health"
          port = 8000
        }
      }
    }
    
    # Scaling configuration
    scaling {
      min_instances = 1
      max_instances = 20
    }
    
    # VPC connector (optional - for private network access)
    # vpc_access {
    #   connector = google_vpc_access_connector.connector.id
    #   egress    = "ALL_TRAFFIC"
    # }
  }
  
  # Traffic splitting (for blue/green deployments)
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  
  # IMPORTANT: Ignore image changes to prevent conflicts with CI/CD
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
  
  depends_on = [
    google_project_service.run_api
  ]
}

# Enable required APIs
resource "google_project_service" "run_api" {
  project = var.project_id
  service = "run.googleapis.com"
  
  disable_on_destroy = false
}

resource "google_project_service" "pubsub_api" {
  project = var.project_id
  service = "pubsub.googleapis.com"
  
  disable_on_destroy = false
}

resource "google_project_service" "bigquery_api" {
  project = var.project_id
  service = "bigquery.googleapis.com"
  
  disable_on_destroy = false
}

# Allow unauthenticated access (restrict in production)
resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.doc_extract.location
  project  = google_cloud_run_v2_service.doc_extract.project
  service  = google_cloud_run_v2_service.doc_extract.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
```

### 2. Create Variables File
File: `infra/variables.tf`

```hcl
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment: dev, staging, production"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}
```

### 3. Create Outputs File
File: `infra/outputs.tf`

```hcl
output "cloud_run_url" {
  description = "URL of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.doc_extract.uri
}

output "service_account_runtime" {
  description = "Runtime service account email"
  value       = google_service_account.doc_extract_runtime.email
}

output "gcs_uploads_bucket" {
  description = "GCS bucket for document uploads"
  value       = google_storage_bucket.uploads.name
}

output "gcs_output_bucket" {
  description = "GCS bucket for extraction output"
  value       = google_storage_bucket.output.name
}

output "pubsub_upload_topic" {
  description = "Pub/Sub topic for document uploads"
  value       = google_pubsub_topic.document_uploaded.name
}

output "bigquery_dataset" {
  description = "BigQuery dataset for results"
  value       = google_bigquery_dataset.extraction.dataset_id
}
```

## Deliverables
- [ ] infra/main.tf with complete infrastructure definition
- [ ] infra/variables.tf with input variables
- [ ] infra/outputs.tf with useful outputs
- [ ] All resources marked as SCAFFOLDING
- [ ] IAM roles documented for each service account
- [ ] Cloud Run lifecycle_ignore_changes for CI/CD compatibility
- [ ] BigQuery schema with nested structures

## Success Criteria
- Terraform files are syntactically valid (terraform validate passes)
- All production components documented: Cloud Run, GCS, Pub/Sub, BigQuery, IAM
- Service accounts have minimal required permissions (principle of least privilege)
- BigQuery table schema matches BorrowerProfile domain model
- lifecycle_ignore_changes configured for Cloud Run image

## Documentation
Include in main.tf:
1. Header comment explaining this is scaffolding
2. ADR reference (002_storage_strategy.md)
3. Deployment instructions
4. IAM requirements by component
5. Scaling limits (min/max instances)

## Next Prompt
After this completes, move to `13_cicd_workflows.md` for GitHub Actions.
