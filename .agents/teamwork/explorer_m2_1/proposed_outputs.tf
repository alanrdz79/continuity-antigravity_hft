# ==============================================================================
# HFT GCP ARCHITECTURE - PUBSUB MODULE OUTPUTS (modules/pubsub/outputs.tf)
# Interfaces for Compute Engine, Dataflow & Safety Orchestration
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Topic Identifiers & Names
# ------------------------------------------------------------------------------

output "trades_topic_id" {
  description = "Unique resource identifier of the market trades Pub/Sub topic."
  value       = google_pubsub_topic.market_trades.id
}

output "trades_topic_name" {
  description = "Name of the market trades Pub/Sub topic."
  value       = google_pubsub_topic.market_trades.name
}

output "orderbook_topic_id" {
  description = "Unique resource identifier of the order book depth Pub/Sub topic."
  value       = google_pubsub_topic.market_orderbook.id
}

output "orderbook_topic_name" {
  description = "Name of the order book depth Pub/Sub topic."
  value       = google_pubsub_topic.market_orderbook.name
}

output "orderbook_depth_topic_id" {
  description = "Unique resource identifier of the orderbook depth alias Pub/Sub topic."
  value       = var.create_orderbook_depth_alias ? google_pubsub_topic.orderbook_depth[0].id : null
}

output "orderbook_depth_topic_name" {
  description = "Name of the orderbook depth alias Pub/Sub topic."
  value       = var.create_orderbook_depth_alias ? google_pubsub_topic.orderbook_depth[0].name : null
}

output "snapshots_topic_id" {
  description = "Unique resource identifier of the order book snapshots Pub/Sub topic."
  value       = google_pubsub_topic.market_snapshots.id
}

output "snapshots_topic_name" {
  description = "Name of the order book snapshots Pub/Sub topic."
  value       = google_pubsub_topic.market_snapshots.name
}

output "safety_alerts_topic_id" {
  description = "Unique resource identifier of the autonomous safety alerts Pub/Sub topic."
  value       = google_pubsub_topic.safety_alerts.id
}

output "safety_alerts_topic_name" {
  description = "Name of the autonomous safety alerts Pub/Sub topic."
  value       = google_pubsub_topic.safety_alerts.name
}

output "safety_alerts_dlq_topic_id" {
  description = "Unique resource identifier of the Dead Letter Queue Pub/Sub topic."
  value       = google_pubsub_topic.safety_alerts_dlq.id
}

output "safety_alerts_dlq_topic_name" {
  description = "Name of the Dead Letter Queue Pub/Sub topic."
  value       = google_pubsub_topic.safety_alerts_dlq.name
}

# ------------------------------------------------------------------------------
# 2. Subscription Identifiers & Names
# ------------------------------------------------------------------------------

output "trades_subscription_id" {
  description = "Resource identifier of the HFT trading engine trades subscription."
  value       = google_pubsub_subscription.trades_engine.id
}

output "trades_subscription_name" {
  description = "Name of the HFT trading engine trades subscription."
  value       = google_pubsub_subscription.trades_engine.name
}

output "orderbook_subscription_id" {
  description = "Resource identifier of the HFT trading engine order book subscription."
  value       = google_pubsub_subscription.orderbook_engine.id
}

output "orderbook_subscription_name" {
  description = "Name of the HFT trading engine order book subscription."
  value       = google_pubsub_subscription.orderbook_engine.name
}

output "dataflow_trades_subscription_id" {
  description = "Resource identifier of the Dataflow streaming trades subscription."
  value       = google_pubsub_subscription.trades_dataflow.id
}

output "dataflow_trades_subscription_name" {
  description = "Name of the Dataflow streaming trades subscription."
  value       = google_pubsub_subscription.trades_dataflow.name
}

output "dataflow_orderbook_subscription_id" {
  description = "Resource identifier of the Dataflow streaming order book subscription."
  value       = google_pubsub_subscription.orderbook_dataflow.id
}

output "dataflow_orderbook_subscription_name" {
  description = "Name of the Dataflow streaming order book subscription."
  value       = google_pubsub_subscription.orderbook_dataflow.name
}

output "snapshots_subscription_id" {
  description = "Resource identifier of the HFT trading engine snapshots subscription."
  value       = google_pubsub_subscription.snapshots_engine.id
}

output "safety_alerts_subscription_id" {
  description = "Resource identifier of the safety alerts / emergency shutdown subscription."
  value       = google_pubsub_subscription.safety_alerts_engine.id
}

output "dlq_subscription_id" {
  description = "Resource identifier of the dead letter queue inspection subscription."
  value       = google_pubsub_subscription.safety_alerts_dlq.id
}

# ------------------------------------------------------------------------------
# 3. Aggregated Topic and Subscription Inventories
# ------------------------------------------------------------------------------

output "all_topic_ids" {
  description = "Map of all provisioned Pub/Sub topic keys to their resource IDs."
  value = merge(
    {
      trades        = google_pubsub_topic.market_trades.id
      orderbook     = google_pubsub_topic.market_orderbook.id
      snapshots     = google_pubsub_topic.market_snapshots.id
      safety_alerts = google_pubsub_topic.safety_alerts.id
      dlq           = google_pubsub_topic.safety_alerts_dlq.id
    },
    var.create_orderbook_depth_alias ? {
      orderbook_depth = google_pubsub_topic.orderbook_depth[0].id
    } : {}
  )
}

output "all_subscription_ids" {
  description = "Map of all provisioned Pub/Sub subscription keys to their resource IDs."
  value = {
    trades_engine      = google_pubsub_subscription.trades_engine.id
    trades_dataflow    = google_pubsub_subscription.trades_dataflow.id
    orderbook_engine   = google_pubsub_subscription.orderbook_engine.id
    orderbook_dataflow = google_pubsub_subscription.orderbook_dataflow.id
    snapshots_engine   = google_pubsub_subscription.snapshots_engine.id
    safety_alerts      = google_pubsub_subscription.safety_alerts_engine.id
    safety_alerts_dlq  = google_pubsub_subscription.safety_alerts_dlq.id
  }
}
