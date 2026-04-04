terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}

# ── Service account ────────────────────────────────────────────────────────────

resource "google_service_account" "tinker" {
  account_id   = "tinker-readonly"
  display_name = "Tinker read-only observability"
}

resource "google_project_iam_member" "logging_viewer" {
  project = var.gcp_project
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.tinker.email}"
}

resource "google_project_iam_member" "monitoring_viewer" {
  project = var.gcp_project
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.tinker.email}"
}

resource "google_project_iam_member" "trace_viewer" {
  project = var.gcp_project
  role    = "roles/cloudtrace.user"
  member  = "serviceAccount:${google_service_account.tinker.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.gcp_project
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.tinker.email}"
}

# ── Secret Manager secrets (values stored externally) ─────────────────────────

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "tinker-anthropic-api-key"
  replication { auto {} }
}

resource "google_secret_manager_secret" "api_keys" {
  secret_id = "tinker-api-keys"
  replication { auto {} }
}

# ── Cloud Run service ─────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "tinker" {
  name     = "tinker"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.tinker.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "TINKER_BACKEND"
        value = var.tinker_backend
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.gcp_project
      }
      env {
        name  = "TINKER_SERVER_PORT"
        value = "8000"
      }

      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TINKER_API_KEYS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_keys.secret_id
            version = "latest"
          }
        }
      }

      liveness_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 15
        period_seconds        = 30
      }
    }
  }
}
