variable "project_id" {
  type        = string
  description = "The GCP Project ID where Secret Manager secrets are provisioned."
}

variable "region" {
  type        = string
  description = "Primary region for secret replication (e.g. asia-northeast1)."
  default     = "asia-northeast1"
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (e.g. production, staging, dev)."
  default     = "production"
}

variable "replication_mode" {
  type        = string
  description = "Secret replication mode: 'user_managed' (locked to region) or 'automatic'."
  default     = "user_managed"
}

variable "hft_engine_sa_email" {
  type        = string
  description = "Email of the HFT trading engine service account (authorized accessor)."
}

variable "emergency_shutdown_sa_email" {
  type        = string
  description = "Email of the Emergency Shutdown function service account (authorized accessor)."
}

variable "binance_api_key" {
  type        = string
  description = "Binance API Key. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_BINANCE_API_KEY_PLACEHOLDER"
  sensitive   = true
}

variable "binance_api_secret" {
  type        = string
  description = "Binance API Secret (HMAC-SHA256). Defaults to safe mock placeholder if omitted."
  default     = "MOCK_BINANCE_API_SECRET_PLACEHOLDER"
  sensitive   = true
}

variable "telegram_bot_token" {
  type        = string
  description = "Telegram Bot Token for alert broadcasts. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_TELEGRAM_BOT_TOKEN_PLACEHOLDER"
  sensitive   = true
}

variable "telegram_chat_id" {
  type        = string
  description = "Telegram Chat ID for panic alerts. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_TELEGRAM_CHAT_ID_PLACEHOLDER"
  sensitive   = true
}

variable "redis_auth_token" {
  type        = string
  description = "Redis AUTH pre-shared string. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_REDIS_AUTH_TOKEN_PLACEHOLDER"
  sensitive   = true
}
