variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "Cloud Run region"
  type        = string
  default     = "us-central1"
}

variable "tinker_backend" {
  description = "Tinker observability backend"
  type        = string
  default     = "gcp"
}

variable "image" {
  description = "Container image to deploy (e.g. gcr.io/PROJECT/tinker:latest)"
  type        = string
  default     = "ghcr.io/tinker-ai/tinker:latest"
}
