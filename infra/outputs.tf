output "api_url" {
  description = "URL of the deployed API"
  value       = google_cloud_run_service.api.status[0].url
}

output "api_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_service.api.name
}

output "documents_bucket" {
  description = "Name of the documents storage bucket"
  value       = google_storage_bucket.documents.name
}

output "processed_bucket" {
  description = "Name of the processed documents bucket"
  value       = google_storage_bucket.processed.name
}

output "pubsub_topic" {
  description = "Name of the Pub/Sub topic"
  value       = google_pubsub_topic.document_events.name
}

output "bigquery_dataset" {
  description = "Name of the BigQuery dataset"
  value       = google_bigquery_dataset.extractions.dataset_id
}

output "service_account_email" {
  description = "Email of the service account"
  value       = google_service_account.doc_extract_sa.email
}
