variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "azure_resource_group" {
  description = "Azure resource group name"
  type        = string
}

variable "azure_location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "azure_workspace_id" {
  description = "Log Analytics workspace ID"
  type        = string
}

variable "tinker_backend" {
  description = "Tinker observability backend"
  type        = string
  default     = "azure"
}

variable "image" {
  description = "Container image to deploy"
  type        = string
  default     = "ghcr.io/tinker-ai/tinker:latest"
}
