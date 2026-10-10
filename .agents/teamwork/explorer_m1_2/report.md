# Milestone 1 Blueprint: Networking Module & VPC Isolation (`modules/networking`)

**Author**: Explorer Subagent (`explorer_m1_2`)  
**Parent Orchestrator**: `orchestrator_hft_gcp` (`922fadba-e6b4-4339-a95e-d2e0ef391991`)  
**Target Path**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\modules\networking`  
**Active GCP Project**: `intrepid-decker-480417-e9`  
**Target Region**: `asia-northeast1` (Tokyo, Japan)  
**Status**: Complete Architectural Blueprint  

---

## 1. Executive Summary & Design Scope

In High-Frequency Trading (HFT) environments executing real-time liquidity and micro-arbitrage strategies against Binance Spot and Binance Predict, the networking topology must fulfill two non-negotiable requirements:
1. **Ultra-Low Latency & Determinism**: The compute infrastructure must reside within minimal physical network distance to Binance matching engines in Tokyo (`asia-northeast1`), avoiding cross-region hops, route flapping, and unnecessary packet buffering.
2. **Zero-Trust VPC Isolation & Zero Public IPs**: Trading nodes must be completely inaccessible from the public internet. No public IPv4 address may ever be attached to the C3/C4 Compute Engine instances. All outbound API orders, WebSocket subscriptions, and telemetries must be securely brokered via Cloud NAT and Private Google Access (PGA), while management access is exclusively tunneled via Google Cloud Identity-Aware Proxy (IAP). Furthermore, state caching in Cloud Memorystore Redis must connect purely through internal Private Service Access (PSA) peering.

This document establishes the production-grade Terraform blueprint for `modules/networking`, including full resource declarations for `variables.tf`, `main.tf`, and `outputs.tf`, dependency chains, port tuning for high-frequency WebSocket streams, and automated validation tests.

---

## 2. Network Topology & Subnetting Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   GOOGLE CLOUD PLATFORM (GCP)                                    │
│                                PROJECT: intrepid-decker-480417-e9                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                 CUSTOM VPC: `hft-vpc`                                            │
│                 (auto_create_subnetworks = false, routing_mode = "REGIONAL")                     │
│                                                                                                  │
│  ┌────────────────────────────────────────────────┐  ┌────────────────────────────────────────┐  │
│  │ PRIMARY HFT SUBNET: `hft-engine-subnet`        │  │ SECONDARY SUBNET: `hft-dataflow-subnet`│  │
│  │ - Region: asia-northeast1 (Tokyo)              │  │ - Region: asia-northeast1 (Tokyo)      │  │
│  │ - CIDR: 10.10.1.0/24                           │  │ - CIDR: 10.10.2.0/24                   │  │
│  │ - private_ip_google_access = true              │  │ - private_ip_google_access = true      │  │
│  │ - Hosts: C3/C4 HFT Engine Nodes (gVNIC)        │  │ - Hosts: Dataflow Streaming Workers    │  │
│  │ - External Public IPs: ZERO (0)                │  │ - External Public IPs: ZERO (0)        │  │
│  └───────────────────────┬────────────────────────┘  └───────────────────┬────────────────────┘  │
│                          │                                               │                       │
│                          └───────────────────────┬───────────────────────┘                       │
│                                                  │                                               │
│                                                  ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                PRIVATE SERVICE ACCESS (PSA) PEERING: `servicenetworking`                   │  │
│  │                - Reserved Global Internal Range: `10.10.16.0/20` (prefix_length = 20)      │  │
│  │                - Service: `servicenetworking.googleapis.com`                               │  │
│  │                - Target Managed Service: Cloud Memorystore for Redis (Standard HA)         │  │
│  │                - Wire Encapsulation: Direct Internal VPC Peering (No Public Transit)       │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                  │                                               │
│                                                  ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                CLOUD ROUTER (`hft-router`) & CLOUD NAT (`hft-nat`)                         │  │
│  │                - Region: asia-northeast1                                                   │  │
│  │                - nat_ip_allocate_option: AUTO_ONLY                                         │  │
│  │                - source_subnetwork_ip_ranges_to_nat: ALL_SUBNETWORKS_ALL_IP_RANGES         │  │
│  │                - min_ports_per_vm: 1024 (Anti-port exhaustion for HFT REST/WS)            │  │
│  │                - tcp_established_idle_timeout_sec: 1200 (Long-lived WebSocket stability)   │  │
│  └───────────────────────────────────────────────┬────────────────────────────────────────────┘  │
│                                                  │ Outbound NAT Egress Only                      │
└──────────────────────────────────────────────────┼───────────────────────────────────────────────┘
                                                   │
                                                   ▼
                         ┌──────────────────────────────────────────────────┐
                         │              PUBLIC INTERNET / IXP               │
                         │      Binance Spot & Predict APIs / Streams       │
                         │      - api.binance.com (REST orders)             │
                         │      - stream.binance.com (L2 Depth WebSocket)   │
                         └──────────────────────────────────────────────────┘
```

### 2.1 Subnetting Scheme & IP Allocation Matrix

| Subnet Identifier | Resource Name | Region | CIDR Block | Usable IPs | Purpose & Workloads |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `subnet_hft` | `hft-engine-subnet` | `asia-northeast1` | `10.10.1.0/24` | 251 | Ultra-low latency C3/C4 Compute Engine nodes. Private Google Access enabled. |
| `subnet_dataflow` | `hft-dataflow-subnet` | `asia-northeast1` | `10.10.2.0/24` | 251 | Apache Beam Dataflow streaming pipeline workers. Private Google Access enabled. |
| `psa_redis_alloc` | `hft-redis-private-ip-alloc` | Global | `10.10.16.0/20` | 4,096 | Reserved internal IP block peered with `servicenetworking.googleapis.com` for Memorystore Redis. |

### 2.2 Regional Routing Mode Rationale
The VPC network resource explicitly specifies `routing_mode = "REGIONAL"`. In high-frequency trading:
- **Global routing** dynamically propagates routes across all Google Cloud regions worldwide, increasing route table convergence times and introducing risks of cross-region routing loops during BGP reconvergences.
- **Regional routing** confines VPC route tables strictly to the `asia-northeast1` control plane. Routing decisions remain localized to the Tokyo datacenter fabric, providing deterministic sub-millisecond packet switching.

### 2.3 Maximum Transmission Unit (MTU)
The VPC is configured with `mtu = 1460` (standard Google Cloud VPC MTU). While C3 instances and gVNIC support jumbo frames (up to 8896 bytes) for intra-VPC communication, outbound traffic to external endpoints (Binance REST and WebSocket APIs over Cloud NAT) traverses standard public transit networks with a maximum MTU of 1500 bytes. Configuring an MTU of 1460 ensures zero packet fragmentation and avoids TCP MSS clamping overhead at the Cloud NAT gateway.

---

## 3. Zero Public IPs & Cloud NAT Egress Architecture

### 3.1 Strict Zero Public IPs Policy
To satisfy the Zero-Trust security requirement and pass automated compliance gates:
- Compute Engine instances provisioned in `hft-engine-subnet` omit the `access_config` block within their `network_interface` declaration.
- Instances possess solely an internal RFC1918 address (e.g. `10.10.1.2`).
- No public IPv4 address is assigned at any point in the VM lifecycle.
- Inbound connections from the public internet are physically impossible at the network layer.

### 3.2 High-Throughput Cloud NAT Optimization for HFT
Trading engines maintain persistent WebSocket streams (`stream.binance.com:9443` or `:443`) and concurrently dispatch hundreds of REST requests per second (`api.binance.com:443`). Standard Google Cloud NAT default settings are tailored for generic web servers and will degrade HFT performance if not tuned:

1. **Anti-Port Exhaustion (`min_ports_per_vm = 1024`)**:
   - Default Cloud NAT assigns only 64 ports per VM. Under rapid order bursts, connection establishment spikes can rapidly exhaust 64 ephemeral ports, leading to connection timeouts and dropped orders.
   - Allocating `min_ports_per_vm = 1024` guarantees an ample pool of source ports per trading VM.
2. **WebSocket Stability (`tcp_established_idle_timeout_sec = 1200`)**:
   - WebSocket streams remain open continuously. Cloud NAT's 1200-second (20 minute) established timeout prevents intermediate state expiration during periods of quiet market ticks.
3. **Connection Cleanup (`tcp_transitory_idle_timeout_sec = 30`)**:
   - Rapidly reclaims ephemeral ports after transient TCP sessions close (e.g., quick REST cancellations).
4. **Log Filtering (`log_config { enable = true, filter = "ERRORS_ONLY" }`)**:
   - Emits logs exclusively for dropped packets, out-of-resource conditions, or NAT translation errors, eliminating log ingestion latency and cost overhead while retaining full observability of network bottlenecks.

---

## 4. Private Service Access (PSA) Peering for Memorystore Redis

Google Cloud Memorystore for Redis instances reside in a Google-managed tenant VPC. Direct private connectivity between `hft-engine-subnet` and Redis requires Private Service Access (PSA):

1. **Global IP Reservation (`google_compute_global_address`)**:
   - Allocated with `purpose = "VPC_PEERING"` and `address_type = "INTERNAL"`.
   - Prefix length set to `20` (`10.10.16.0/20`), allocating a clean `/20` block that does not overlap with `10.10.1.0/24` or `10.10.2.0/24`.
2. **Service Peering Connection (`google_service_networking_connection`)**:
   - Binds `hft-vpc` to `servicenetworking.googleapis.com`.
   - Establishes bi-directional VPC peering between the customer VPC and Google's internal service network.
3. **Critical Downstream Dependency Contract**:
   - In Terraform, creating `google_redis_instance` before PSA peering finishes will result in an immediate `INVALID_ARGUMENT` or `RESOURCE_NOT_FOUND` error.
   - The networking module exports `private_service_access_connection = google_service_networking_connection.private_vpc_connection.id`.
   - The storage module / root orchestrator must declare:
     ```hcl
     depends_on = [module.networking.private_service_access_connection]
     ```

---

## 5. Zero-Trust Firewall Perimeter

The firewall configuration implements a strict Default-Deny architecture:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              VPC FIREWALL SECURITY RULES                               │
├──────────────────────────┬──────────┬───────────┬──────────────────────────────────────┤
│ Rule Name                │ Direction│ Priority  │ Allowed Traffic / Source Range       │
├──────────────────────────┼──────────┼───────────┼──────────────────────────────────────┤
│ hft-deny-all-ingress     │ INGRESS  │ 65000     │ Deny ALL from 0.0.0.0/0              │
│ hft-allow-internal       │ INGRESS  │ 1000      │ Allow TCP/UDP/ICMP from 10.10.0.0/16 │
│ hft-allow-iap-ssh        │ INGRESS  │ 1000      │ Allow TCP 22 from 35.235.240.0/20    │
│ (default-allow-egress)   │ EGRESS   │ 65535     │ Allow outbound via Cloud NAT & PGA   │
└──────────────────────────┴──────────┴───────────┴──────────────────────────────────────┘
```

1. **Explicit Ingress Block (`hft-deny-all-ingress`)**:
   - Denies all inbound protocols from `0.0.0.0/0` at priority 65000.
2. **Internal VPC Communication (`hft-allow-internal`)**:
   - Allows all traffic sourced from within the VPC CIDR `10.10.0.0/16`.
   - Enables the C3/C4 trading VM to query Memorystore Redis on port 6379, communicate with Dataflow workers, and ingest internal metric probes.
3. **IAP Secure Management Access (`hft-allow-iap-ssh`)**:
   - Restricted strictly to Google Cloud Identity-Aware Proxy CIDR `35.235.240.0/20` on TCP port 22.
   - Operators and CI/CD tools connect using cryptographic IAP tunnels:
     ```powershell
     gcloud compute ssh hft-trading-engine-01 --zone=asia-northeast1-b --tunnel-through-iap
     ```
   - Eliminates the need for bastion hosts or public IP jumps.

---

## 6. Implementation Blueprint: `modules/networking` Code Specification

The module is structured cleanly into three files:
- `variables.tf`: Input parameters with defaults.
- `main.tf`: Core GCP networking resources.
- `outputs.tf`: Exported attributes fulfilling interface contracts.

### 6.1 `modules/networking/variables.tf`

```hcl
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
  default     = "hft-vpc"
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
```

### 6.2 `modules/networking/main.tf`

```hcl
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

  min_ports_per_vm                   = var.nat_min_ports_per_vm
  tcp_established_idle_timeout_sec   = 1200
  tcp_transitory_idle_timeout_sec    = 30

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
```

### 6.3 `modules/networking/outputs.tf`

```hcl
output "network_id" {
  description = "The unique identifier of the created VPC network"
  value       = google_compute_network.hft_vpc.id
}

output "network_name" {
  description = "The name of the created VPC network"
  value       = google_compute_network.hft_vpc.name
}

output "network_self_link" {
  description = "The URI self link of the created VPC network"
  value       = google_compute_network.hft_vpc.self_link
}

output "subnet_hft_id" {
  description = "The unique identifier of the primary HFT engine subnet"
  value       = google_compute_subnetwork.hft_engine_subnet.id
}

output "subnet_hft_name" {
  description = "The name of the primary HFT engine subnet"
  value       = google_compute_subnetwork.hft_engine_subnet.name
}

output "subnet_hft_cidr" {
  description = "The IP CIDR range of the primary HFT engine subnet"
  value       = google_compute_subnetwork.hft_engine_subnet.ip_cidr_range
}

output "subnet_dataflow_id" {
  description = "The unique identifier of the secondary Dataflow worker subnet"
  value       = google_compute_subnetwork.hft_dataflow_subnet.id
}

output "subnet_dataflow_name" {
  description = "The name of the secondary Dataflow worker subnet"
  value       = google_compute_subnetwork.hft_dataflow_subnet.name
}

output "subnet_dataflow_cidr" {
  description = "The IP CIDR range of the secondary Dataflow worker subnet"
  value       = google_compute_subnetwork.hft_dataflow_subnet.ip_cidr_range
}

output "router_id" {
  description = "The unique identifier of the Cloud Router"
  value       = google_compute_router.hft_router.id
}

output "nat_id" {
  description = "The unique identifier of the Cloud NAT gateway"
  value       = google_compute_router_nat.hft_nat.id
}

output "private_service_access_connection" {
  description = "The Private Service Access connection resource ID for Memorystore Redis dependency chaining"
  value       = google_service_networking_connection.private_vpc_connection.id
}
```

---

## 7. Downstream Integration Contracts & Dependency Graph

```
                               ┌─────────────────────────────┐
                               │     Root main.tf Module     │
                               └──────────────┬──────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │                                               │
                      ▼                                               ▼
        ┌───────────────────────────┐                   ┌───────────────────────────┐
        │  google_project_service   │                   │    modules/iam            │
        │  - compute.googleapis.com │                   │    - sa-hft-engine        │
        │  - servicenetworking      │                   │    - sa-dataflow-worker   │
        └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                      │ depends_on                                    │
                      ▼                                               │
        ┌───────────────────────────┐                                 │
        │    modules/networking     │                                 │
        │    - hft-vpc              │                                 │
        │    - hft-engine-subnet    │                                 │
        │    - hft-dataflow-subnet  │                                 │
        │    - Cloud NAT & Router   │                                 │
        │    - PSA Peering Link     │                                 │
        └──────┬─────────────┬──────┘                                 │
               │             │                                        │
    network_id │             │ private_service_access_connection      │
    subnet_id  │             │ (depends_on link)                      │
               ▼             ▼                                        ▼
   ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────────────┐
   │   modules/compute    │  │   modules/storage    │  │     modules/dataflow      │
   │   - C3/C4 Instance   │  │   - Memorystore Redis│  │     - Streaming Pipeline  │
   │   - gVNIC Enabled    │  │     (Standard HA)    │  │     - Private Workers     │
   │   - 0 Public IPs     │  │   - Cloud Bigtable   │  │                           │
   └──────────────────────┘  └──────────────────────┘  └───────────────────────────┘
```

### 7.1 Module Invocation Snippet in Root `main.tf`
```hcl
module "networking" {
  source = "./modules/networking"

  project_id      = var.project_id
  region          = var.region
  network_name    = "hft-vpc"
  routing_mode    = "REGIONAL"
  subnet_hft_cidr = "10.10.1.0/24"
  subnet_dataflow_cidr = "10.10.2.0/24"

  depends_on = [
    google_project_service.enabled_apis["compute.googleapis.com"],
    google_project_service.enabled_apis["servicenetworking.googleapis.com"]
  ]
}
```

### 7.2 Storage (Redis) Invocation Linking to PSA Peering
```hcl
module "storage_redis" {
  source = "./modules/storage_redis"

  project_id = var.project_id
  region     = var.region
  network_id = module.networking.network_id

  depends_on = [
    module.networking.private_service_access_connection
  ]
}
```

---

## 8. Verification & Acceptance Testing Specification

### 8.1 Automated Test Gates for Milestone 1
The implementer and automated auditor must verify the following properties:

| Check # | Target Resource | Verification Command / Probe | Success Condition |
| :--- | :--- | :--- | :--- |
| **TC-1** | VPC Network Mode | `gcloud compute networks describe hft-vpc --format="value(routingConfig.routingMode)"` | Returns `"REGIONAL"` |
| **TC-2** | Auto Subnets Disabled | `gcloud compute networks describe hft-vpc --format="value(autoCreateSubnetworks)"` | Returns `False` |
| **TC-3** | Primary Subnet PGA | `gcloud compute networks subnets describe hft-engine-subnet --region=asia-northeast1 --format="value(privateIpGoogleAccess)"` | Returns `True` |
| **TC-4** | Secondary Subnet PGA | `gcloud compute networks subnets describe hft-dataflow-subnet --region=asia-northeast1 --format="value(privateIpGoogleAccess)"` | Returns `True` |
| **TC-5** | PSA Peering Status | `gcloud compute networks peerings list --network=hft-vpc --format="value(peerings[0].state)"` | Returns `"ACTIVE"` |
| **TC-6** | Cloud NAT Min Ports | `gcloud compute routers nats describe hft-nat --router=hft-router --region=asia-northeast1 --format="value(minPortsPerVm)"` | Returns `1024` |
| **TC-7** | Zero Public IPs | Python scanner `verify_security_posture.py` auditing `accessConfigs` | Zero instances with public IPs |
| **TC-8** | IAP Firewall Scope | `gcloud compute firewall-rules describe hft-allow-iap-ssh --format="value(sourceRanges)"` | Matches `['35.235.240.0/20']` |

---

## 9. Next Steps for Implementation Worker (`worker_m1`)

1. Create target directory `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\modules\networking\`.
2. Write `variables.tf`, `main.tf`, and `outputs.tf` using the exact code blueprints detailed in Section 6.
3. Validate syntax and dependency references via `terraform fmt` and `terraform validate`.
4. Expose the outputs to the root module for consumption by Milestone 2 (Compute & Pub/Sub) and Milestone 3 (Storage & Redis).
