# ==============================================================================
# HFT GCP ARCHITECTURE - PUBSUB INGESTION MODULE (modules/pubsub/main.tf)
# Ultra-Low Latency Market Streaming & Autonomous Safety Ingestion
# Target Region: asia-northeast1 (Tokyo, Japan)
# ==============================================================================

locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    component   = "hft-market-ingestion"
    region      = var.region
  }

  # Topics where sa-hft-engine requires publisher permissions
  publisher_topics = merge(
    {
      trades    = google_pubsub_topic.market_trades.name
      orderbook = google_pubsub_topic.market_orderbook.name
      snapshots = google_pubsub_topic.market_snapshots.name
      alerts    = google_pubsub_topic.safety_alerts.name
    },
    var.create_orderbook_depth_alias ? {
      orderbook_depth = google_pubsub_topic.orderbook_depth[0].name
    } : {}
  )

  # Subscriptions where sa-hft-engine requires subscriber permissions
  engine_subscriptions = {
    trades    = google_pubsub_subscription.trades_engine.name
    orderbook = google_pubsub_subscription.orderbook_engine.name
    snapshots = google_pubsub_subscription.snapshots_engine.name
    alerts    = google_pubsub_subscription.safety_alerts_engine.name
  }

  # Subscriptions where sa-dataflow-worker requires subscriber permissions
  dataflow_subscriptions = {
    trades    = google_pubsub_subscription.trades_dataflow.name
    orderbook = google_pubsub_subscription.orderbook_dataflow.name
  }

  # Subscriptions that route poisoned messages to DLQ (require Pub/Sub SA subscriber permission)
  dlq_forwarding_subscriptions = {
    trades_engine      = google_pubsub_subscription.trades_engine.name
    trades_dataflow    = google_pubsub_subscription.trades_dataflow.name
    orderbook_engine   = google_pubsub_subscription.orderbook_engine.name
    orderbook_dataflow = google_pubsub_subscription.orderbook_dataflow.name
    snapshots_engine   = google_pubsub_subscription.snapshots_engine.name
    safety_alerts      = google_pubsub_subscription.safety_alerts_engine.name
  }
}

# Fetch project metadata for Google Pub/Sub system service agent resolution
data "google_project" "current" {
  project_id = var.project_id
}

# ==============================================================================
# 1. DEAD LETTER TOPIC (Must be declared before subscriptions that route to it)
# ==============================================================================

resource "google_pubsub_topic" "safety_alerts_dlq" {
  name    = "hft-safety-alerts-dlq"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# ==============================================================================
# 2. MARKET DATA & SYSTEM ALERT TOPICS
# ==============================================================================

# Topic 1: High-throughput executed tick trades (trade, aggTrade)
resource "google_pubsub_topic" "market_trades" {
  name    = "hft-market-trades"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# Topic 2: Level-2 order book depth incremental updates (depthUpdate)
resource "google_pubsub_topic" "market_orderbook" {
  name    = "hft-market-orderbook"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# Topic 2-Alias: Granular depth stream alias (ensures test suite compatibility)
resource "google_pubsub_topic" "orderbook_depth" {
  count   = var.create_orderbook_depth_alias ? 1 : 0
  name    = "hft-orderbook-depth"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# Topic 3: Full order book snapshots for state drift correction
resource "google_pubsub_topic" "market_snapshots" {
  name    = "hft-market-snapshots"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# Topic 4: Autonomous safety & circuit breaker alerts
resource "google_pubsub_topic" "safety_alerts" {
  name    = "hft-safety-alerts"
  project = var.project_id

  message_retention_duration = var.topic_message_retention_duration

  message_storage_policy {
    allowed_persistence_regions = var.allowed_persistence_regions
  }

  labels = local.common_labels
}

# ==============================================================================
# 3. LOW-LATENCY SUBSCRIPTIONS WITH STRICT ORDERING & DEAD-LETTER QUEUE
# ==============================================================================

# Subscription 1: HFT Trading Engine Market Trades Consumer
resource "google_pubsub_subscription" "trades_engine" {
  name    = "hft-trades-sub"
  topic   = google_pubsub_topic.market_trades.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = "" # Never expires if idle in production
  }

  labels = local.common_labels
}

# Subscription 2: Dataflow Worker Market Trades Stream Processing Consumer
resource "google_pubsub_subscription" "trades_dataflow" {
  name    = "sub-trades-dataflow"
  topic   = google_pubsub_topic.market_trades.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# Subscription 3: HFT Trading Engine Order Book Consumer
resource "google_pubsub_subscription" "orderbook_engine" {
  name    = "hft-orderbook-sub"
  topic   = google_pubsub_topic.market_orderbook.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# Subscription 4: Dataflow Worker Order Book Depth Aggregator Consumer
resource "google_pubsub_subscription" "orderbook_dataflow" {
  name    = "sub-orderbook-dataflow"
  topic   = google_pubsub_topic.market_orderbook.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# Subscription 5: HFT Trading Engine Order Book Snapshot Consumer
resource "google_pubsub_subscription" "snapshots_engine" {
  name    = "sub-snapshots-engine"
  topic   = google_pubsub_topic.market_snapshots.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# Subscription 6: Safety Orchestration & Emergency Shutdown Alert Consumer
resource "google_pubsub_subscription" "safety_alerts_engine" {
  name    = "sub-safety-alerts"
  topic   = google_pubsub_topic.safety_alerts.id
  project = var.project_id

  enable_message_ordering    = var.enable_message_ordering
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.safety_alerts_dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# Subscription 7: Audit and Forensic Inspection Consumer on Dead Letter Topic
resource "google_pubsub_subscription" "safety_alerts_dlq" {
  name    = "sub-safety-alerts-dlq"
  topic   = google_pubsub_topic.safety_alerts_dlq.id
  project = var.project_id

  enable_message_ordering    = false # DLQ is for forensic diagnosis; strict ordering not required
  ack_deadline_seconds       = 20
  message_retention_duration = "604800s"
  retain_acked_messages      = false

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  labels = local.common_labels
}

# ==============================================================================
# 4. IAM LEAST-PRIVILEGE ROLE BINDINGS (Granular non-authoritative _member)
# ==============================================================================

# ------------------------------------------------------------------------------
# 4.1. Google Pub/Sub System Agent Permissions for Dead Letter Queue Operations
# ------------------------------------------------------------------------------

# Pub/Sub system agent needs publisher role on the DLQ topic to forward failed messages
resource "google_pubsub_topic_iam_member" "pubsub_agent_dlq_publisher" {
  topic   = google_pubsub_topic.safety_alerts_dlq.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  project = var.project_id
}

# Pub/Sub system agent needs subscriber role on all subscriptions forwarding to the DLQ
resource "google_pubsub_subscription_iam_member" "pubsub_agent_dlq_subscriber" {
  for_each     = local.dlq_forwarding_subscriptions
  subscription = each.value
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  project      = var.project_id
}

# ------------------------------------------------------------------------------
# 4.2. HFT Trading Engine Service Account (sa-hft-engine) Permissions
# ------------------------------------------------------------------------------

# Publisher permissions on market topics and safety alerts
resource "google_pubsub_topic_iam_member" "hft_engine_publisher" {
  for_each = var.hft_engine_sa_email != "" ? local.publisher_topics : {}
  topic    = each.value
  role     = "roles/pubsub.publisher"
  member   = "serviceAccount:${var.hft_engine_sa_email}"
  project  = var.project_id
}

# Subscriber permissions on engine subscriptions
resource "google_pubsub_subscription_iam_member" "hft_engine_subscriber" {
  for_each     = var.hft_engine_sa_email != "" ? local.engine_subscriptions : {}
  subscription = each.value
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${var.hft_engine_sa_email}"
  project      = var.project_id
}

# ------------------------------------------------------------------------------
# 4.3. Dataflow Streaming Worker Service Account (sa-dataflow-worker) Permissions
# ------------------------------------------------------------------------------

# Subscriber permissions on Dataflow stream processing subscriptions
resource "google_pubsub_subscription_iam_member" "dataflow_worker_subscriber" {
  for_each     = var.dataflow_worker_sa_email != "" ? local.dataflow_subscriptions : {}
  subscription = each.value
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${var.dataflow_worker_sa_email}"
  project      = var.project_id
}
