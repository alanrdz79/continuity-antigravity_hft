# ==============================================================================
# HFT GCP ARCHITECTURE - CLOUD BIGTABLE TICK STORAGE MODULE
# Target File Location for Implementation: modules/storage/bigtable.tf
# Target Region / Zone: asia-northeast1-c (Tokyo, Japan)
# Primary Engine: Low-Latency High-Frequency Trading Tick & Depth Storage
# Storage Type: STRICTLY SSD (Zero HDD latency overhead)
# ==============================================================================

locals {
  # Resolved cluster zone: defaults to secondary_zone (asia-northeast1-c) for storage isolation
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
}

# ------------------------------------------------------------------------------
# 1. Cloud Bigtable Production SSD Instance & Cluster
# ------------------------------------------------------------------------------
resource "google_bigtable_instance" "tick_store" {
  name                 = var.bigtable_instance_name
  project              = var.project_id
  display_name         = var.bigtable_display_name
  deletion_protection  = var.deletion_protection
  labels               = local.bigtable_labels

  cluster {
    cluster_id   = var.bigtable_cluster_id
    zone         = local.resolved_bigtable_zone
    storage_type = "SSD" # Strictly SSD for deterministic sub-millisecond HFT read/write latencies
    num_nodes    = var.enable_bigtable_autoscaling ? null : var.bigtable_num_nodes

    dynamic "autoscaling_config" {
      for_each = var.enable_bigtable_autoscaling ? [1] : []
      content {
        min_nodes  = var.bigtable_min_nodes
        max_nodes  = var.bigtable_max_nodes
        cpu_target = var.bigtable_cpu_target
      }
    }
  }

  lifecycle {
    prevent_destroy = false
  }
}

# ------------------------------------------------------------------------------
# 2. Primary Market Ticks Table: hft-market-ticks
# ------------------------------------------------------------------------------
resource "google_bigtable_table" "market_ticks" {
  name          = var.market_ticks_table_name
  instance_name = google_bigtable_instance.tick_store.name
  project       = var.project_id
  split_keys    = var.market_ticks_split_keys

  # Column Family 't' (trades): Execution events, taker side, fills, trade IDs
  column_family {
    family = "t"
  }

  # Column Family 'q' (quotes): L2 top-of-book depth, microprice, book imbalance
  column_family {
    family = "q"
  }

  # Column Family 'm' (metrics): Engine latency, feed latency, queue delay, volatility
  column_family {
    family = "m"
  }

  lifecycle {
    prevent_destroy = false
  }
}

# ------------------------------------------------------------------------------
# 3. Garbage Collection (GC) Policies for Market Ticks
# ------------------------------------------------------------------------------

# GC Policy for Trades ('t'): Retain executions for 30 days (720h)
resource "google_bigtable_gc_policy" "trades_gc" {
  instance_name   = google_bigtable_instance.tick_store.name
  table           = google_bigtable_table.market_ticks.name
  column_family   = "t"
  project         = var.project_id
  deletion_policy = "ABANDON"

  max_age {
    duration = var.gc_trades_max_age
  }
}

# GC Policy for Quotes ('q'): Retain ultra-high-volume L2 depth for 7 days (168h)
resource "google_bigtable_gc_policy" "quotes_gc" {
  instance_name   = google_bigtable_instance.tick_store.name
  table           = google_bigtable_table.market_ticks.name
  column_family   = "q"
  project         = var.project_id
  deletion_policy = "ABANDON"

  max_age {
    duration = var.gc_quotes_max_age
  }
}

# GC Policy for Metrics ('m'): Retain statistical and latency metrics for 14 days (336h)
resource "google_bigtable_gc_policy" "metrics_gc" {
  instance_name   = google_bigtable_instance.tick_store.name
  table           = google_bigtable_table.market_ticks.name
  column_family   = "m"
  project         = var.project_id
  deletion_policy = "ABANDON"

  max_age {
    duration = var.gc_metrics_max_age
  }
}

# ------------------------------------------------------------------------------
# 4. Optional / Auxiliary Tables (Snapshots & Execution Reports)
# ------------------------------------------------------------------------------

resource "google_bigtable_table" "orderbook_snapshots" {
  count         = var.enable_auxiliary_tables ? 1 : 0
  name          = var.orderbook_snapshots_table_name
  instance_name = google_bigtable_instance.tick_store.name
  project       = var.project_id

  column_family {
    family = "snapshots"
  }

  column_family {
    family = "metadata"
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "google_bigtable_gc_policy" "orderbook_snapshots_gc" {
  count           = var.enable_auxiliary_tables ? 1 : 0
  instance_name   = google_bigtable_instance.tick_store.name
  table           = google_bigtable_table.orderbook_snapshots[0].name
  column_family   = "snapshots"
  project         = var.project_id
  deletion_policy = "ABANDON"

  max_age {
    duration = "72h" # Keep full L2 snapshots for 3 days
  }
}

resource "google_bigtable_table" "execution_reports" {
  count         = var.enable_auxiliary_tables ? 1 : 0
  name          = var.execution_reports_table_name
  instance_name = google_bigtable_instance.tick_store.name
  project       = var.project_id

  column_family {
    family = "orders"
  }

  column_family {
    family = "fills"
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "google_bigtable_gc_policy" "execution_reports_gc" {
  count           = var.enable_auxiliary_tables ? 1 : 0
  instance_name   = google_bigtable_instance.tick_store.name
  table           = google_bigtable_table.execution_reports[0].name
  column_family   = "orders"
  project         = var.project_id
  deletion_policy = "ABANDON"

  max_age {
    duration = "720h" # Keep order execution lifecycle for 30 days
  }
}

# ------------------------------------------------------------------------------
# 5. Fine-Grained Least-Privilege IAM Bindings (Instance-Level)
# ------------------------------------------------------------------------------

# Binding 1: Low-latency C3/C4 Trading Engine VM (sa-hft-engine)
resource "google_bigtable_instance_iam_member" "hft_engine_user" {
  count    = var.hft_engine_sa_email != "" ? 1 : 0
  instance = google_bigtable_instance.tick_store.name
  project  = var.project_id
  role     = "roles/bigtable.user"
  member   = "serviceAccount:${var.hft_engine_sa_email}"
}

# Binding 2: Streaming Apache Beam Dataflow Worker (sa-dataflow-worker)
resource "google_bigtable_instance_iam_member" "dataflow_worker_user" {
  count    = var.dataflow_worker_sa_email != "" ? 1 : 0
  instance = google_bigtable_instance.tick_store.name
  project  = var.project_id
  role     = "roles/bigtable.user"
  member   = "serviceAccount:${var.dataflow_worker_sa_email}"
}
