variable "project_id" {
  description = "The GCP project ID where networking resources are created"
  type        = string
}

variable "region" {
  description = "The primary GCP region for HFT networking resources (e.g. asia-northeast1)"
  type        = string
  default     = "asia-northeast1"
}

variable "network_name" {
  description = "The name of the custom VPC network"
  type        = string
  default     = "hft-primary-vpc"
}

variable "routing_mode" {
  description = "The network routing mode (REGIONAL recommended for HFT determinism)"
  type        = string
  default     = "REGIONAL"
}

variable "mtu" {
  description = "The Maximum Transmission Unit (MTU) in bytes for the VPC"
  type        = number
  default     = 1460
}

variable "subnet_hft_name" {
  description = "Name of the primary HFT Compute Engine subnet"
  type        = string
  default     = "hft-engine-subnet"
}

variable "subnet_hft_cidr" {
  description = "CIDR block for the primary HFT Compute Engine subnet"
  type        = string
  default     = "10.10.1.0/24"
}

variable "subnet_dataflow_name" {
  description = "Name of the secondary Dataflow worker subnet"
  type        = string
  default     = "hft-dataflow-subnet"
}

variable "subnet_dataflow_cidr" {
  description = "CIDR block for the secondary Dataflow worker subnet"
  type        = string
  default     = "10.10.2.0/24"
}

variable "psa_address_name" {
  description = "Name of the global internal address allocation for Private Service Access (Redis)"
  type        = string
  default     = "hft-redis-private-ip-alloc"
}

variable "psa_prefix_length" {
  description = "Prefix length for Private Service Access allocation block (/20 allocates 4096 IPs)"
  type        = number
  default     = 20
}

variable "router_name" {
  description = "Name of the Cloud Router managing Cloud NAT"
  type        = string
  default     = "hft-router"
}

variable "nat_name" {
  description = "Name of the Cloud NAT gateway"
  type        = string
  default     = "hft-nat"
}

variable "nat_min_ports_per_vm" {
  description = "Minimum ports allocated per VM to prevent port exhaustion under high REST/WS volume"
  type        = number
  default     = 1024
}

variable "environment" {
  description = "Deployment environment tag (production, staging, demo)"
  type        = string
  default     = "production"
}
