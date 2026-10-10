# variables.tf - Global Input Variables for HFT GCP Architecture
# Project: intrepid-decker-480417-e9
# Region: asia-northeast1 (Tokyo, Japan - lowest latency to Binance matching engines)

variable "project_id" {
  description = "The GCP project ID where all HFT infrastructure resources are provisioned"
  type        = string
  default     = "intrepid-decker-480417-e9"
}

variable "region" {
  description = "Target GCP region for ultra-low latency to Binance matching engines (Tokyo)"
  type        = string
  default     = "asia-northeast1"
}

variable "primary_zone" {
  description = "Primary zone for C3/C4 ultra-low latency trading VMs (Sapphire/Emerald Rapids)"
  type        = string
  default     = "asia-northeast1-b"
}

variable "secondary_zone" {
  description = "Secondary zone for Bigtable replication and HA caching"
  type        = string
  default     = "asia-northeast1-c"
}

variable "environment" {
  description = "Deployment environment name (production, staging, development)"
  type        = string
  default     = "production"
}

variable "machine_type" {
  description = "Compute Engine machine type for trading engine (c3-standard-4 or c4-standard-4 with gVNIC)"
  type        = string
  default     = "c3-standard-4"
}

variable "vpc_name" {
  description = "Name of the custom isolated VPC network"
  type        = string
  default     = "hft-primary-vpc"
}

variable "subnet_cidr_primary" {
  description = "CIDR range for primary HFT trading subnet in asia-northeast1-b"
  type        = string
  default     = "10.10.1.0/24"
}

variable "subnet_cidr_secondary" {
  description = "CIDR range for secondary subnet in asia-northeast1-c"
  type        = string
  default     = "10.10.2.0/24"
}

variable "redis_memory_size_gb" {
  description = "Memory capacity in GiB for Memorystore Redis instance"
  type        = number
  default     = 5
}

variable "gcp_services" {
  description = "List of GCP APIs to enable for the HFT autonomous architecture"
  type        = list(string)
  default = [
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "bigtable.googleapis.com",
    "redis.googleapis.com",
    "eventarc.googleapis.com",
    "cloudfunctions.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com"
  ]
}
