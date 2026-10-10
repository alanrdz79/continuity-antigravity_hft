# ==============================================================================
# 1. Custom VPC Network
# ==============================================================================
resource "google_compute_network" "hft_vpc" {
  name                            = var.network_name
  project                         = var.project_id
  auto_create_subnetworks         = false
  routing_mode                    = var.routing_mode
  mtu                             = var.mtu
  delete_default_routes_on_create = false

  description = "Isolated custom VPC for CONTINUITY HFT Low-Latency Trading Architecture"
}

# ==============================================================================
# 2. Dedicated Regional Subnets
# ==============================================================================

# Primary Subnet: Low-Latency C3/C4 Compute Engine Trading Node
resource "google_compute_subnetwork" "hft_engine_subnet" {
  name                     = var.subnet_hft_name
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.hft_vpc.id
  ip_cidr_range            = var.subnet_hft_cidr
  private_ip_google_access = true

  description = "Dedicated subnet for low-latency C3/C4 HFT trading instances (Zero Public IPs)"
}

# Secondary Subnet: Dataflow Stream Processing Workers
resource "google_compute_subnetwork" "hft_dataflow_subnet" {
  name                     = var.subnet_dataflow_name
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.hft_vpc.id
  ip_cidr_range            = var.subnet_dataflow_cidr
  private_ip_google_access = true

  description = "Subnet for Apache Beam Dataflow stream processing workers"
}

# ==============================================================================
# 3. Cloud Router & High-Throughput Cloud NAT Gateway
# ==============================================================================
resource "google_compute_router" "hft_router" {
  name    = var.router_name
  project = var.project_id
  region  = var.region
  network = google_compute_network.hft_vpc.id

  description = "Cloud Router managing outbound NAT for HFT trading and Dataflow subnets"
}

resource "google_compute_router_nat" "hft_nat" {
  name                               = var.nat_name
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.hft_router.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  min_ports_per_vm                 = var.nat_min_ports_per_vm
  tcp_established_idle_timeout_sec = 1200
  tcp_transitory_idle_timeout_sec  = 30

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ==============================================================================
# 4. Private Service Access (PSA) Peering for Memorystore Redis
# ==============================================================================

# Reserved internal IP address range for Service Networking peering
resource "google_compute_global_address" "hft_psa_address" {
  name          = var.psa_address_name
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = "10.10.16.0"
  prefix_length = var.psa_prefix_length
  network       = google_compute_network.hft_vpc.id

  description = "Internal IP allocation block for Google Managed Services (Redis)"
}

# VPC Peering Connection to Google Service Networking
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.hft_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.hft_psa_address.name]
}

# ==============================================================================
# 5. Zero-Trust Firewall Rules
# ==============================================================================

# Ingress: Explicit Deny All from Public Internet
resource "google_compute_firewall" "deny_all_ingress" {
  name      = "hft-deny-all-ingress"
  project   = var.project_id
  network   = google_compute_network.hft_vpc.name
  direction = "INGRESS"
  priority  = 65000

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  description   = "Explicit baseline deny for all incoming public internet traffic"
}

# Ingress: Allow Internal VPC Communication (Engine <-> Redis, Dataflow <-> Redis)
resource "google_compute_firewall" "allow_internal" {
  name      = "hft-allow-internal"
  project   = var.project_id
  network   = google_compute_network.hft_vpc.name
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.10.0.0/16"]
  description   = "Allow all internal communication within the HFT VPC CIDR block"
}

# Ingress: Allow Management via Google Cloud Identity-Aware Proxy (IAP)
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "hft-allow-iap-ssh"
  project   = var.project_id
  network   = google_compute_network.hft_vpc.name
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["hft-engine", "hft-node"]
  description   = "Allow SSH management strictly through Google Cloud IAP cryptographic tunnel"
}
