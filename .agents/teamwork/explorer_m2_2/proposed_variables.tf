# variables.tf - Input Variables for Compute Engine HFT Trading Node Module
# Architecture: Ultra-Low Latency C3/C4 Compute in Tokyo (asia-northeast1)

variable "project_id" {
  description = "The GCP project ID where the compute resources will be created"
  type        = string
}

variable "region" {
  description = "Target GCP region (e.g. asia-northeast1 for Tokyo)"
  type        = string
  default     = "asia-northeast1"
}

variable "zone" {
  description = "GCP Zone for trading engine instance (verified available for C3/C4: asia-northeast1-b or asia-northeast1-c)"
  type        = string
  default     = null
}

variable "primary_zone" {
  description = "Primary target GCP zone (alias for zone, matches root main.tf)"
  type        = string
  default     = "asia-northeast1-b"
}

variable "environment" {
  description = "Deployment environment name (production, staging, development)"
  type        = string
  default     = "production"
}

variable "instance_name" {
  description = "Base name for the HFT trading engine Compute Engine instance"
  type        = string
  default     = "hft-engine-node-01"
}

variable "instance_count" {
  description = "Number of trading engine instances to deploy in the compact placement policy group"
  type        = number
  default     = 1
}

variable "machine_type" {
  description = "Compute Engine machine type for trading engine (defaulting to C4 Emerald Rapids with fallback to C3 Sapphire Rapids)"
  type        = string
  default     = "c4-standard-4"
  validation {
    condition = contains([
      "c4-standard-4",
      "c4-standard-8",
      "c4-highcpu-4",
      "c4-highcpu-8",
      "c3-standard-4",
      "c3-standard-8",
      "c3-highcpu-4",
      "c3-highcpu-8",
      "c2-standard-4",
      "n2-standard-4"
    ], var.machine_type)
    error_message = "The machine_type must be a high-performance instance type supporting gVNIC (e.g. c4-standard-4, c3-standard-4)."
  }
}

variable "network_id" {
  description = "The VPC network ID or self link where the instance interface is connected"
  type        = string
}

variable "subnet_id" {
  description = "The subnet ID or self link for the HFT private network interface (module.networking.subnet_hft_id)"
  type        = string
}

variable "service_account_email" {
  description = "The service account email attached to the instance (module.iam.hft_engine_sa_email)"
  type        = string
}

variable "source_image" {
  description = "Operating system image family or URI for trading node (e.g. debian-cloud/debian-12 or ubuntu-os-cloud/ubuntu-2204-lts)"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "boot_disk_type" {
  description = "Disk type for root boot disk. Note: C4 machine family requires 'hyperdisk-balanced', while C3 supports 'hyperdisk-balanced' and 'pd-ssd'. If null, automatically selects hyperdisk-balanced for C4 and pd-ssd for C3."
  type        = string
  default     = null
}

variable "boot_disk_size_gb" {
  description = "Size of the root boot disk in GiB"
  type        = number
  default     = 100
}

variable "enable_placement_policy" {
  description = "Whether to attach a compact collocated placement policy to the instance"
  type        = bool
  default     = true
}

variable "custom_startup_script" {
  description = "Optional custom startup script string. If provided, overrides default network tuning startup script."
  type        = string
  default     = null
}

variable "labels" {
  description = "Labels to assign to the compute instance"
  type        = map(string)
  default = {
    workload    = "hft-trading-engine"
    tier        = "compute-execution"
    collocation = "compact"
  }
}
