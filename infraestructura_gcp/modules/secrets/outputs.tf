output "secret_ids" {
  description = "Map of secret names to fully qualified secret IDs."
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}

output "binance_api_key_secret_id" {
  description = "Fully qualified ID for the Binance API key secret."
  value       = google_secret_manager_secret.secrets["binance-api-key"].id
}

output "binance_api_secret_secret_id" {
  description = "Fully qualified ID for the Binance API secret."
  value       = google_secret_manager_secret.secrets["binance-api-secret"].id
}

output "telegram_bot_token_secret_id" {
  description = "Fully qualified ID for the Telegram bot token secret."
  value       = google_secret_manager_secret.secrets["telegram-bot-token"].id
}

output "telegram_chat_id_secret_id" {
  description = "Fully qualified ID for the Telegram chat ID secret."
  value       = google_secret_manager_secret.secrets["telegram-chat-id"].id
}

output "redis_auth_token_secret_id" {
  description = "Fully qualified ID for the Redis AUTH token secret."
  value       = google_secret_manager_secret.secrets["redis-auth-token"].id
}
