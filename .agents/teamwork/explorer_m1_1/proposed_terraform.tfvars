# terraform.tfvars - Environment-Specific Variables for HFT Production Architecture
# Project: intrepid-decker-480417-e9

project_id           = "intrepid-decker-480417-e9"
region               = "asia-northeast1"
primary_zone         = "asia-northeast1-b"
secondary_zone       = "asia-northeast1-c"
environment          = "production"
machine_type         = "c3-standard-4"
vpc_name             = "hft-primary-vpc"
subnet_cidr_primary  = "10.10.1.0/24"
subnet_cidr_secondary = "10.10.2.0/24"
redis_memory_size_gb = 5
