# ==============================================================================
# HFT GCP ARCHITECTURE - STORAGE & STATE CACHING MODULE
# Location: modules/storage/main.tf
# Target Region: asia-northeast1 (Tokyo, Japan)
# Primary Components: Cloud Bigtable SSD (bigtable.tf) & Cloud Memorystore Redis HA (redis.tf)
# ==============================================================================

locals {
  # Resolved Bigtable cluster zone: defaults to secondary_zone (asia-northeast1-c) for storage isolation
  resolved_bigtable_zone = coalesce(var.bigtable_zone, var.secondary_zone, "${var.region}-c")

  bigtable_labels = merge(
    {
      environment = var.environment
      managed_by  = "terraform"
      component   = "tick-storage"
      engine      = "cloud-bigtable"
    },
    var.labels
  )

  redis_labels = merge(
    {
      environment = var.environment
      component   = "redis-state-cache"
      workload    = "hft-trading"
      managed_by  = "terraform"
    },
    var.labels
  )
}
