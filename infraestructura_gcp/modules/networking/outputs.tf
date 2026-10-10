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
