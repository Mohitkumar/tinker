terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.80"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
}

# ── Key Vault ──────────────────────────────────────────────────────────────────

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "tinker" {
  name                = "tinker-vault"
  location            = var.azure_location
  resource_group_name = var.azure_resource_group
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Purge protection required for managed identity access
  purge_protection_enabled = true
}

# Allow the deploying principal to manage secrets during setup
resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.tinker.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "List", "Set", "Delete"]
}

# ── Container App environment ─────────────────────────────────────────────────

resource "azurerm_container_app_environment" "tinker" {
  name                = "tinker-env"
  location            = var.azure_location
  resource_group_name = var.azure_resource_group
}

# ── Container App ─────────────────────────────────────────────────────────────

resource "azurerm_container_app" "tinker" {
  name                         = "tinker"
  container_app_environment_id = azurerm_container_app_environment.tinker.id
  resource_group_name          = var.azure_resource_group
  revision_mode                = "Single"

  # System-assigned managed identity — used for Key Vault and Log Analytics access
  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = false   # internal only — expose via APIM or VPN gateway
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name                = "anthropic-api-key"
    key_vault_secret_id = "${azurerm_key_vault.tinker.vault_uri}secrets/anthropic-api-key"
    identity            = "System"
  }
  secret {
    name                = "tinker-api-keys"
    key_vault_secret_id = "${azurerm_key_vault.tinker.vault_uri}secrets/tinker-api-keys"
    identity            = "System"
  }

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name   = "tinker"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "TINKER_BACKEND"
        value = var.tinker_backend
      }
      env {
        name  = "AZURE_LOG_ANALYTICS_WORKSPACE_ID"
        value = var.azure_workspace_id
      }
      env {
        name  = "AZURE_SUBSCRIPTION_ID"
        value = var.azure_subscription_id
      }
      env {
        name  = "AZURE_RESOURCE_GROUP"
        value = var.azure_resource_group
      }
      env {
        name  = "TINKER_SERVER_PORT"
        value = "8000"
      }
      env {
        name        = "ANTHROPIC_API_KEY"
        secret_name = "anthropic-api-key"
      }
      env {
        name        = "TINKER_API_KEYS"
        secret_name = "tinker-api-keys"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        initial_delay        = 15
        interval_seconds     = 30
        failure_count_threshold = 3
      }
    }
  }
}

# ── Role assignments for the managed identity ─────────────────────────────────

resource "azurerm_role_assignment" "monitoring_reader" {
  scope                = "/subscriptions/${var.azure_subscription_id}"
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_container_app.tinker.identity[0].principal_id
}

resource "azurerm_role_assignment" "log_analytics_reader" {
  scope                = "/subscriptions/${var.azure_subscription_id}"
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_container_app.tinker.identity[0].principal_id
}

resource "azurerm_key_vault_access_policy" "tinker_app" {
  key_vault_id = azurerm_key_vault.tinker.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_container_app.tinker.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}
