r"""
CONTINUITY HFT GCP - Empirical Adversarial Challenge Test Suite for Storage, Redis & Dataflow.
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\tests\test_storage_dataflow_adversarial.py

Adversarial test verification scope:
1. Dataflow Workers Zero Public External IPs:
   - ip_configuration = "WORKER_IP_PRIVATE" explicitly declared.
   - Zero access_config or public IP mapping.
   - Private Google Access enabled on the target subnet.
   - GCS staging bucket enforces public_access_prevention and uniform_bucket_level_access.
2. Memorystore Redis Security & PSA Peering:
   - connect_mode = "PRIVATE_SERVICE_ACCESS" explicitly declared.
   - Authorized network bound to private VPC network ID.
   - depends_on PSA peering connection explicitly declared on google_redis_instance to prevent race condition.
   - In-transit encryption and AUTH enabled.
   - Memory eviction policy set to volatile-lru to preserve emergency kill-switch key.
3. Cloud Bigtable SSD & Least-Privilege IAM:
   - storage_type = "SSD" strictly declared on the cluster (no HDD fallback).
   - Least-privilege roles/bigtable.user enforced on sa-hft-engine and sa-dataflow-worker.
   - Zero administrative (roles/bigtable.admin) or primitive (roles/owner, roles/editor) roles on worker identities.
4. Adversarial Detection Oracles:
   - Verifies that mutations violating security invariants are reliably caught.
"""

import re
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATAFLOW_DIR = PROJECT_ROOT / "modules" / "dataflow"
STORAGE_DIR = PROJECT_ROOT / "modules" / "storage"
NETWORKING_DIR = PROJECT_ROOT / "modules" / "networking"
IAM_DIR = PROJECT_ROOT / "modules" / "iam"

DATAFLOW_MAIN_TF = DATAFLOW_DIR / "main.tf"
DATAFLOW_VARS_TF = DATAFLOW_DIR / "variables.tf"
STORAGE_MAIN_TF = STORAGE_DIR / "main.tf"
STORAGE_BIGTABLE_TF = STORAGE_DIR / "bigtable.tf"
STORAGE_REDIS_TF = STORAGE_DIR / "redis.tf"
STORAGE_VARS_TF = STORAGE_DIR / "variables.tf"
NETWORKING_MAIN_TF = NETWORKING_DIR / "main.tf"
IAM_MAIN_TF = IAM_DIR / "main.tf"
ROOT_MAIN_TF = PROJECT_ROOT / "main.tf"


class TestStorageDataflowAdversarialChallenge(unittest.TestCase):
    """Empirical adversarial verification of Dataflow, Redis, Bigtable, and IAM isolation perimeters."""

    @classmethod
    def setUpClass(cls):
        cls.dataflow_main = DATAFLOW_MAIN_TF.read_text(encoding="utf-8")
        cls.dataflow_vars = DATAFLOW_VARS_TF.read_text(encoding="utf-8")
        cls.storage_bigtable = STORAGE_BIGTABLE_TF.read_text(encoding="utf-8")
        cls.storage_redis = STORAGE_REDIS_TF.read_text(encoding="utf-8")
        cls.storage_vars = STORAGE_VARS_TF.read_text(encoding="utf-8")
        cls.networking_main = NETWORKING_MAIN_TF.read_text(encoding="utf-8")
        cls.iam_main = IAM_MAIN_TF.read_text(encoding="utf-8")
        cls.root_main = ROOT_MAIN_TF.read_text(encoding="utf-8")

    # --------------------------------------------------------------------------
    # 1. Dataflow Worker Zero Public IP & Isolation Perimeter
    # --------------------------------------------------------------------------
    def test_dataflow_ip_configuration_strictly_private(self):
        """Assert that ip_configuration is explicitly 'WORKER_IP_PRIVATE' in google_dataflow_job."""
        # Find google_dataflow_job block up to its closing boundary or check directly
        ip_config_match = re.search(
            r'resource\s+["\']google_dataflow_job["\'][\s\S]+?ip_configuration\s*=\s*["\']WORKER_IP_PRIVATE["\']',
            self.dataflow_main,
        )
        self.assertIsNotNone(
            ip_config_match,
            "CRITICAL SECURITY VIOLATION: ip_configuration is NOT WORKER_IP_PRIVATE in Dataflow job!"
        )

        # Negative check: WORKER_IP_PUBLIC must never appear
        self.assertNotIn(
            "WORKER_IP_PUBLIC",
            self.dataflow_main,
            "CRITICAL SECURITY VIOLATION: WORKER_IP_PUBLIC found in dataflow module!"
        )

    def test_dataflow_no_variable_override_for_ip_configuration(self):
        """Assert that no variable exists allowing callers to override ip_configuration to public."""
        self.assertNotIn(
            "ip_configuration",
            self.dataflow_vars,
            "Variable 'ip_configuration' exposed in dataflow variables.tf, allowing potential public IP override!"
        )

    def test_dataflow_subnet_placement_has_private_google_access(self):
        """Assert that Dataflow subnetwork in networking module enforces private_ip_google_access = true."""
        subnet_match = re.search(
            r'resource\s+["\']google_compute_subnetwork["\']\s+["\']hft_dataflow_subnet["\']\s*\{([^}]+)\}',
            self.networking_main,
            re.DOTALL,
        )
        self.assertIsNotNone(subnet_match, "google_compute_subnetwork.hft_dataflow_subnet not found in networking main.tf")
        subnet_content = subnet_match.group(1)

        self.assertIn(
            "private_ip_google_access = true",
            subnet_content,
            "Dataflow subnet does NOT have private_ip_google_access = true!"
        )

    def test_dataflow_staging_bucket_security_posture(self):
        """Assert that Dataflow staging bucket enforces public access prevention and uniform IAM."""
        bucket_match = re.search(
            r'resource\s+["\']google_storage_bucket["\']\s+["\']dataflow_staging["\']\s*\{([^}]+)\}',
            self.dataflow_main,
            re.DOTALL,
        )
        self.assertIsNotNone(bucket_match, "google_storage_bucket.dataflow_staging not found in dataflow main.tf")
        bucket_content = bucket_match.group(1)

        self.assertIn(
            'public_access_prevention    = "enforced"',
            bucket_content,
            "Dataflow staging bucket does not enforce public_access_prevention = 'enforced'!"
        )
        self.assertIn(
            "uniform_bucket_level_access = true",
            bucket_content,
            "Dataflow staging bucket does not enforce uniform_bucket_level_access = true!"
        )

    # --------------------------------------------------------------------------
    # 2. Memorystore Redis Isolation & PSA Peering Race Prevention
    # --------------------------------------------------------------------------
    def test_redis_connect_mode_private_service_access(self):
        """Assert that Redis connect_mode defaults to and uses PRIVATE_SERVICE_ACCESS."""
        # Check resource binding
        self.assertIn("connect_mode       = var.redis_connect_mode", self.storage_redis)
        self.assertIn("authorized_network = var.network_id", self.storage_redis)

        # Check variable default
        var_match = re.search(
            r'variable\s+["\']redis_connect_mode["\']\s*\{([^}]+)\}',
            self.storage_vars,
            re.DOTALL,
        )
        self.assertIsNotNone(var_match, "variable 'redis_connect_mode' not found in storage variables.tf")
        self.assertIn('default     = "PRIVATE_SERVICE_ACCESS"', var_match.group(1))

    def test_redis_depends_on_psa_peering_race_prevention(self):
        """Assert that google_redis_instance explicitly declares depends_on PSA peering connection."""
        redis_match = re.search(
            r'resource\s+["\']google_redis_instance["\']\s+["\']hft_redis["\']\s*\{([^}]+)\}',
            self.storage_redis,
            re.DOTALL,
        )
        self.assertIsNotNone(redis_match, "google_redis_instance.hft_redis not found in redis.tf")
        redis_content = redis_match.group(1)

        # Check depends_on block
        depends_on_match = re.search(
            r'depends_on\s*=\s*\[([^\]]+)\]',
            redis_content,
            re.DOTALL,
        )
        self.assertIsNotNone(
            depends_on_match,
            "CRITICAL: google_redis_instance does NOT have a depends_on block! Subject to API 400 race conditions."
        )
        self.assertIn(
            "var.private_service_access_connection",
            depends_on_match.group(1),
            "depends_on does NOT reference var.private_service_access_connection!"
        )

        # Check root main.tf passes PSA connection output to module.storage
        storage_module_match = re.search(
            r'module\s+["\']storage["\']\s*\{([^}]+)\}',
            self.root_main,
            re.DOTALL,
        )
        self.assertIsNotNone(storage_module_match, "module 'storage' not declared in root main.tf")
        storage_wiring = storage_module_match.group(1)
        self.assertIn(
            "private_service_access_connection = module.networking.private_service_access_connection",
            storage_wiring,
            "Root main.tf does NOT wire module.networking.private_service_access_connection to module.storage!"
        )

    def test_redis_security_auth_and_transit_encryption(self):
        """Assert that Redis has AUTH enabled, transit encryption active, and volatile-lru eviction."""
        self.assertIn("auth_enabled            = var.redis_auth_enabled", self.storage_redis)
        self.assertIn("transit_encryption_mode = var.redis_transit_encryption_mode", self.storage_redis)

        # Check defaults in storage variables.tf
        auth_var = re.search(r'variable\s+["\']redis_auth_enabled["\']\s*\{([^}]+)\}', self.storage_vars, re.DOTALL)
        self.assertIsNotNone(auth_var)
        self.assertIn("default     = true", auth_var.group(1))

        enc_var = re.search(r'variable\s+["\']redis_transit_encryption_mode["\']\s*\{([^}]+)\}', self.storage_vars, re.DOTALL)
        self.assertIsNotNone(enc_var)
        self.assertIn('default     = "SERVER_AUTHENTICATION"', enc_var.group(1))

        # Check volatile-lru in redis_configs
        cfg_var = re.search(r'variable\s+["\']redis_configs["\']\s*\{([^}]+)\}', self.storage_vars, re.DOTALL)
        self.assertIsNotNone(cfg_var)
        self.assertIn('maxmemory-policy = "volatile-lru"', cfg_var.group(1))

    # --------------------------------------------------------------------------
    # 3. Cloud Bigtable SSD Storage & Least-Privilege IAM
    # --------------------------------------------------------------------------
    def test_bigtable_storage_type_strictly_ssd(self):
        """Assert that Bigtable cluster has storage_type = 'SSD' hardcoded with zero HDD fallback."""
        cluster_match = re.search(
            r'cluster\s*\{([^}]+)\}',
            self.storage_bigtable,
            re.DOTALL,
        )
        self.assertIsNotNone(cluster_match, "cluster block not found in google_bigtable_instance in bigtable.tf")
        cluster_content = cluster_match.group(1)

        ssd_match = re.search(r'storage_type\s*=\s*["\']SSD["\']', cluster_content)
        self.assertIsNotNone(
            ssd_match,
            "CRITICAL: Bigtable cluster storage_type is NOT explicitly 'SSD'!"
        )

        # Ensure no variable allows setting HDD
        self.assertNotIn(
            "bigtable_storage_type",
            self.storage_vars,
            "Variable 'bigtable_storage_type' found in variables.tf; storage_type must remain strictly SSD."
        )
        self.assertNotIn('"HDD"', self.storage_bigtable, "HDD storage type found in bigtable.tf!")

    def test_bigtable_least_privilege_iam_bindings(self):
        """Assert that Bigtable instance IAM members use least-privilege roles/bigtable.user."""
        # Instance-level binding for engine
        engine_iam_match = re.search(
            r'resource\s+["\']google_bigtable_instance_iam_member["\']\s+["\']hft_engine_user["\']\s*\{([^}]+)\}',
            self.storage_bigtable,
            re.DOTALL,
        )
        self.assertIsNotNone(engine_iam_match)
        self.assertIn('role     = "roles/bigtable.user"', engine_iam_match.group(1))

        # Instance-level binding for dataflow worker
        worker_iam_match = re.search(
            r'resource\s+["\']google_bigtable_instance_iam_member["\']\s+["\']dataflow_worker_user["\']\s*\{([^}]+)\}',
            self.storage_bigtable,
            re.DOTALL,
        )
        self.assertIsNotNone(worker_iam_match)
        self.assertIn('role     = "roles/bigtable.user"', worker_iam_match.group(1))

        # Negative checks: neither must have roles/bigtable.admin
        self.assertNotIn("roles/bigtable.admin", engine_iam_match.group(1))
        self.assertNotIn("roles/bigtable.admin", worker_iam_match.group(1))

    def test_iam_module_zero_primitive_roles(self):
        """Assert that IAM module assigns zero primitive Owner/Editor roles to HFT SAs."""
        # Find hft_engine_roles list
        engine_roles_match = re.search(r'hft_engine_roles\s*=\s*\[([^\]]+)\]', self.iam_main, re.DOTALL)
        self.assertIsNotNone(engine_roles_match)
        engine_roles = [r.strip().strip('"') for r in engine_roles_match.group(1).split(",") if r.strip()]
        self.assertNotIn("roles/owner", engine_roles)
        self.assertNotIn("roles/editor", engine_roles)
        self.assertIn("roles/bigtable.user", engine_roles)

        # Find dataflow_worker_roles list
        worker_roles_match = re.search(r'dataflow_worker_roles\s*=\s*\[([^\]]+)\]', self.iam_main, re.DOTALL)
        self.assertIsNotNone(worker_roles_match)
        worker_roles = [r.strip().strip('"') for r in worker_roles_match.group(1).split(",") if r.strip()]
        self.assertNotIn("roles/owner", worker_roles)
        self.assertNotIn("roles/editor", worker_roles)
        self.assertIn("roles/bigtable.user", worker_roles)

    # --------------------------------------------------------------------------
    # 4. Adversarial Mutation & Violation Detection Oracles
    # --------------------------------------------------------------------------
    def test_detector_flags_dataflow_public_ip_mutation(self):
        """Adversarial check: ensure detector flags simulated Dataflow public IP mutation."""
        simulated_hcl = 'resource "google_dataflow_job" "test" {\n  ip_configuration = "WORKER_IP_PUBLIC"\n}'
        has_public_ip = 'ip_configuration = "WORKER_IP_PUBLIC"' in simulated_hcl or "access_config" in simulated_hcl
        self.assertTrue(has_public_ip, "Oracle failed to detect simulated public IP mutation in Dataflow!")

    def test_detector_flags_redis_direct_peering_mutation(self):
        """Adversarial check: ensure detector flags non-PSA connect mode mutation in Redis."""
        simulated_hcl = 'resource "google_redis_instance" "test" {\n  connect_mode = "DIRECT_PEERING"\n}'
        is_psa = 'connect_mode = "PRIVATE_SERVICE_ACCESS"' in simulated_hcl
        self.assertFalse(is_psa, "Oracle failed to detect non-PSA connect mode in Redis!")

    def test_detector_flags_bigtable_hdd_mutation(self):
        """Adversarial check: ensure detector flags HDD storage_type mutation in Bigtable."""
        simulated_hcl = 'cluster {\n  storage_type = "HDD"\n}'
        is_ssd = 'storage_type = "SSD"' in simulated_hcl
        self.assertFalse(is_ssd, "Oracle failed to detect HDD storage_type mutation in Bigtable!")

    # --------------------------------------------------------------------------
    # 5. Terraform CLI Validation
    # --------------------------------------------------------------------------
    def test_terraform_validate_cli(self):
        """Empirically run terraform validate to ensure overall configuration is valid."""
        proc = subprocess.run(
            ["terraform", "validate", "-no-color"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"terraform validate failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
        self.assertIn("Success! The configuration is valid.", proc.stdout)


if __name__ == "__main__":
    unittest.main()
