output "app_fqdn" {
  description = "Container App FQDN — add https://<fqdn> to tinker.toml [server] url"
  value       = azurerm_container_app.tinker.ingress[0].fqdn
}

output "managed_identity_principal_id" {
  description = "Managed identity principal ID (for additional role assignments)"
  value       = azurerm_container_app.tinker.identity[0].principal_id
}

output "key_vault_uri" {
  description = "Key Vault URI for storing additional secrets"
  value       = azurerm_key_vault.tinker.vault_uri
}
