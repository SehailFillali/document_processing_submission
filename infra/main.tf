terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev, staging, production)"
  type        = string
  default     = "dev"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "documents" {
  name          = "${var.project_id}-doc-extract-${var.environment}"
  location      = var.region
  storage_class = "STANDARD"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "processed" {
  name          = "${var.project_id}-doc-extract-processed-${var.environment}"
  location      = var.region
  storage_class = "STANDARD"
}

resource "google_pubsub_topic" "document_events" {
  name = "document-events-${var.environment}"
}

resource "google_pubsub_topic" "dlq" {
  name = "document-events-dlq-${var.environment}"
}

resource "google_pubsub_subscription" "document_processing" {
  name  = "document-processing-${var.environment}"
  topic = google_pubsub_topic.document_events.name

  ack_deadline_seconds = 60

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_bigquery_dataset" "extractions" {
  dataset_id    = "document_extractions_${var.environment}"
  friendly_name = "Document Extractions"
  description   = "Extracted data from documents"
  location      = var.region
}

resource "google_bigquery_table" "borrower_profiles" {
  dataset_id = google_bigquery_dataset.extractions.dataset_id
  table_id   = "borrower_profiles"

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  schema = <<EOF
[
  {"name": "borrower_id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "name", "type": "STRING", "mode": "REQUIRED"},
  {"name": "ssn_last_four", "type": "STRING", "mode": "NULLABLE"},
  {"name": "address", "type": "JSON", "mode": "NULLABLE"},
  {"name": "income_history", "type": "JSON", "mode": "NULLABLE"},
  {"name": "accounts", "type": "JSON", "mode": "NULLABLE"},
  {"name": "confidence_score", "type": "FLOAT", "mode": "NULLABLE"},
  {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"}
]
EOF
}

resource "google_cloud_run_service" "api" {
  name     = "doc-extract-api-${var.environment}"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/doc-extract:latest"

        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
      }

      service_account_name = "doc-extract-sa@${var.project_id}.iam.gserviceaccount.com"
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "google_service_account" "doc_extract_sa" {
  account_id   = "doc-extract-sa"
  display_name = "Document Extraction Service Account"
  description  = "Service account for document extraction service"
}

resource "google_project_iam_member" "doc_extract_roles" {
  for_each = toset([
    "roles/storage.objectAdmin",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.doc_extract_sa.email}"
}

output "api_url" {
  value = google_cloud_run_service.api.status[0].url
}

output "bucket_name" {
  value = google_storage_bucket.documents.name
}
