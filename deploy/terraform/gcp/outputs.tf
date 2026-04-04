output "service_url" {
  description = "Cloud Run service URL — add to tinker.toml [server] url"
  value       = google_cloud_run_v2_service.tinker.uri
}

output "service_account_email" {
  description = "Service account email for Workload Identity binding"
  value       = google_service_account.tinker.email
}
