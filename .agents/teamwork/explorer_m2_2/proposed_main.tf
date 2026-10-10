# main.tf - Compute Engine Module for High-Frequency Trading Node
# Provisioned in: asia-northeast1 (Tokyo, Japan)
# Machine Families: C4 (Emerald Rapids) / C3 (Sapphire Rapids) with Titanium IPU

locals {
  # Resolve zone from either 'zone' or 'primary_zone' variable
  effective_zone = coalesce(var.zone, var.primary_zone, "asia-northeast1-b")

  # C4 instances require hyperdisk-balanced; C3 supports pd-ssd and hyperdisk-balanced
  default_disk_type = startswith(var.machine_type, "c4") ? "hyperdisk-balanced" : "pd-ssd"
  resolved_disk_type = var.boot_disk_type != null ? var.boot_disk_type : local.default_disk_type

  # Default startup script if custom script is not supplied
  default_startup_script = file("${path.module}/startup_script.sh")
  effective_startup_script = var.custom_startup_script != null ? var.custom_startup_script : local.default_startup_script

  common_labels = merge(
    {
      environment = var.environment
      managed_by  = "terraform"
      component   = "trading-engine"
    },
    var.labels
  )
}

# ------------------------------------------------------------------------------
# 1. Compact Placement Policy (Intra-Rack Collocation)
# ------------------------------------------------------------------------------
# Forces instances into the same physical rack / availability domain
# to achieve sub-microsecond intra-node network latencies.
resource "google_compute_resource_policy" "compact_placement" {
  count       = var.enable_placement_policy ? 1 : 0
  name        = "${var.environment}-hft-compact-placement"
  project     = var.project_id
  region      = var.region
  description = "Compact collocated placement policy for ultra-low latency intra-rack clustering"

  group_placement_policy {
    collocation = "COLLOCATED"
    vm_count    = var.instance_count
  }
}

# ------------------------------------------------------------------------------
# 2. C3 / C4 Ultra-Low Latency Compute Engine Trading Instance
# ------------------------------------------------------------------------------
resource "google_compute_instance" "trading_engine" {
  name         = "${var.environment}-${var.instance_name}"
  project      = var.project_id
  machine_type = var.machine_type
  zone         = local.effective_zone
  description  = "HFT trading engine instance with gVNIC, Tier 1 networking, and zero public IPs"

  # Compact placement policy attachment
  resource_policies = var.enable_placement_policy ? [google_compute_resource_policy.compact_placement[0].id] : []

  # Boot Disk configuration (NVMe SSD / Hyperdisk Balanced)
  boot_disk {
    auto_delete = true
    device_name = "hft-boot-disk"

    initialize_params {
      image = var.source_image
      size  = var.boot_disk_size_gb
      type  = local.resolved_disk_type
      labels = {
        environment = var.environment
        disk_role   = "boot"
      }
    }
  }

  # Network Interface: Private isolated subnet, gVNIC enabled, ZERO access_config
  network_interface {
    network    = var.network_id
    subnetwork = var.subnet_id
    nic_type   = "GVNIC" # Mandatory for C3/C4 and Tier 1 bandwidth

    # CRITICAL SECURITY RULE:
    # ZERO access_config block ensures 0 public external IP addresses.
    # Outbound API connectivity (Binance, Telegram) routes securely via Cloud NAT.
  }

  # Tier 1 Network Bandwidth: Unlocks up to 50-100 Gbps egress line rates
  network_performance_config {
    total_egress_bandwidth_tier = "TIER_1"
  }

  # Least-Privilege Service Account Binding
  service_account {
    email  = var.service_account_email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  # Metadata Startup Script: Applies kernel sysctl tuning and audits 0 public IPs
  metadata_startup_script = local.effective_startup_script

  metadata = {
    enable-oslogin = "TRUE"
    hft-tuned      = "true"
  }

  # Scheduling: Live migration for high availability during maintenance
  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    provisioning_model  = "STANDARD"
  }

  # Shielded VM Configuration: Protects against rootkits and unauthorized boot code
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  labels = local.common_labels

  tags = [
    "hft-trading-node",
    "private-workload",
    "${var.environment}-hft"
  ]
}
