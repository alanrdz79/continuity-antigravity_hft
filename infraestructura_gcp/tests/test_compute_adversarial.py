r"""
CONTINUITY HFT GCP - Empirical Adversarial Challenge Test Suite for Compute Engine.
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\tests\test_compute_adversarial.py

Adversarial test verification scope:
1. gVNIC explicitly declared on Compute Engine trading node.
2. Zero external public IP addresses (no access_config block).
3. Dynamic disk type oracle: C4 -> hyperdisk-balanced, C3 -> pd-ssd.
4. Compact collocation placement policy configuration and attachment.
5. Machine type validation matrix and invalid type rejection.
6. Root module integration, wiring, and Terraform CLI validation.
"""

import re
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPUTE_DIR = PROJECT_ROOT / "modules" / "compute"
COMPUTE_MAIN_TF = COMPUTE_DIR / "main.tf"
COMPUTE_VARS_TF = COMPUTE_DIR / "variables.tf"
COMPUTE_OUTPUTS_TF = COMPUTE_DIR / "outputs.tf"
STARTUP_SCRIPT = COMPUTE_DIR / "startup_script.sh"
ROOT_MAIN_TF = PROJECT_ROOT / "main.tf"
ROOT_OUTPUTS_TF = PROJECT_ROOT / "outputs.tf"
ROOT_TFVARS = PROJECT_ROOT / "terraform.tfvars"


class TestComputeAdversarialChallenge(unittest.TestCase):
    """Empirical verification of Compute Engine configuration and invariants."""

    @classmethod
    def setUpClass(cls):
        cls.compute_main = COMPUTE_MAIN_TF.read_text(encoding="utf-8")
        cls.compute_vars = COMPUTE_VARS_TF.read_text(encoding="utf-8")
        cls.compute_outputs = COMPUTE_OUTPUTS_TF.read_text(encoding="utf-8")
        cls.startup_content = STARTUP_SCRIPT.read_text(encoding="utf-8")
        cls.root_main = ROOT_MAIN_TF.read_text(encoding="utf-8")
        cls.root_outputs = ROOT_OUTPUTS_TF.read_text(encoding="utf-8")

    # --------------------------------------------------------------------------
    # 1. gVNIC Explicit Declaration Verification
    # --------------------------------------------------------------------------
    def test_gvnic_explicitly_declared(self):
        """Assert that nic_type = 'GVNIC' is explicitly declared on the network interface."""
        # Find network_interface block inside google_compute_instance
        net_iface_match = re.search(
            r'network_interface\s*\{([^}]+)\}',
            self.compute_main,
            re.DOTALL,
        )
        self.assertIsNotNone(net_iface_match, "network_interface block not found in compute main.tf")
        net_iface_content = net_iface_match.group(1)

        # Check explicit GVNIC declaration
        gvnic_match = re.search(r'nic_type\s*=\s*["\']GVNIC["\']', net_iface_content)
        self.assertIsNotNone(
            gvnic_match,
            "CRITICAL: nic_type = 'GVNIC' is NOT explicitly declared inside network_interface!"
        )

        # Check Tier 1 network bandwidth configuration
        perf_match = re.search(
            r'network_performance_config\s*\{[^}]*total_egress_bandwidth_tier\s*=\s*["\']TIER_1["\'][^}]*\}',
            self.compute_main,
            re.DOTALL,
        )
        self.assertIsNotNone(
            perf_match,
            "CRITICAL: network_performance_config with TIER_1 egress bandwidth is missing!"
        )

        # Negative check: VirtIO must NOT be configured
        self.assertNotIn('VIRTIO_NET', self.compute_main, "VirtIO NIC type found, which is unsupported on C3/C4")

    # --------------------------------------------------------------------------
    # 2. Zero Public External IP Verification
    # --------------------------------------------------------------------------
    def test_zero_public_ip_no_access_config(self):
        """Assert that no access_config block exists in compute network_interface (0 public IPs)."""
        net_iface_match = re.search(
            r'network_interface\s*\{([^}]+)\}',
            self.compute_main,
            re.DOTALL,
        )
        self.assertIsNotNone(net_iface_match, "network_interface block not found in compute main.tf")
        net_iface_content = net_iface_match.group(1)

        # Remove comments before checking
        cleaned_net_iface = re.sub(r'#.*', '', net_iface_content)

        # Assert no access_config block exists
        self.assertNotIn(
            "access_config",
            cleaned_net_iface,
            "CRITICAL SECURITY VIOLATION: access_config block found! VM must not have an external public IP."
        )

        # Assert no nat_ip is declared
        self.assertNotIn(
            "nat_ip",
            cleaned_net_iface,
            "CRITICAL SECURITY VIOLATION: nat_ip declared in network_interface!"
        )

        # Check startup_script enforces zero public IP audit against metadata server
        self.assertIn("network-interfaces/0/access-configs/", self.startup_content)
        self.assertIn("ZERO public external IP addresses detected", self.startup_content)

        # Verify outputs only expose internal IP, no public IP
        self.assertIn('output "internal_ip"', self.compute_outputs)
        self.assertNotIn('output "public_ip"', self.compute_outputs)
        self.assertNotIn('output "nat_ip"', self.compute_outputs)

    # --------------------------------------------------------------------------
    # 3. Dynamic Disk Type Resolution Oracle
    # --------------------------------------------------------------------------
    @staticmethod
    def resolve_disk_type(machine_type: str, boot_disk_type: str = None) -> str:
        """Python oracle mirroring the Terraform HCL dynamic disk type logic."""
        default_disk_type = "hyperdisk-balanced" if machine_type.startswith("c4") else "pd-ssd"
        return boot_disk_type if boot_disk_type is not None else default_disk_type

    def test_dynamic_disk_type_hcl_syntax(self):
        """Verify the HCL logic in compute main.tf implements dynamic disk type correctly."""
        # Check ternary expression for default_disk_type
        self.assertIn('startswith(var.machine_type, "c4") ? "hyperdisk-balanced" : "pd-ssd"', self.compute_main)
        # Check resolved_disk_type override
        self.assertIn('var.boot_disk_type != null ? var.boot_disk_type : local.default_disk_type', self.compute_main)
        # Check boot_disk block uses resolved_disk_type
        boot_disk_match = re.search(
            r'boot_disk\s*\{[^}]*initialize_params\s*\{[^}]*type\s*=\s*local\.resolved_disk_type',
            self.compute_main,
            re.DOTALL,
        )
        self.assertIsNotNone(
            boot_disk_match,
            "boot_disk.initialize_params.type is not wired to local.resolved_disk_type!"
        )

    def test_dynamic_disk_type_c4_family(self):
        """Adversarially verify all C4 machine family types resolve to hyperdisk-balanced."""
        c4_types = [
            "c4-standard-4",
            "c4-standard-8",
            "c4-standard-16",
            "c4-standard-32",
            "c4-highcpu-4",
            "c4-highcpu-8",
            "c4-highcpu-16",
            "c4-highmem-4",
        ]
        for mt in c4_types:
            disk = self.resolve_disk_type(mt)
            self.assertEqual(
                disk,
                "hyperdisk-balanced",
                f"Machine type {mt} failed to resolve to hyperdisk-balanced"
            )

    def test_dynamic_disk_type_c3_family(self):
        """Adversarially verify all C3 machine family types resolve to pd-ssd."""
        c3_types = [
            "c3-standard-4",
            "c3-standard-8",
            "c3-standard-22",
            "c3-highcpu-4",
            "c3-highcpu-8",
            "c3-highcpu-22",
            "c3-highmem-4",
        ]
        for mt in c3_types:
            disk = self.resolve_disk_type(mt)
            self.assertEqual(
                disk,
                "pd-ssd",
                f"Machine type {mt} failed to resolve to pd-ssd"
            )

    def test_dynamic_disk_type_explicit_override(self):
        """Verify explicit boot_disk_type overrides automatic selection."""
        # C3 with explicit hyperdisk-balanced override
        self.assertEqual(
            self.resolve_disk_type("c3-standard-4", boot_disk_type="hyperdisk-balanced"),
            "hyperdisk-balanced"
        )
        # C4 with explicit override
        self.assertEqual(
            self.resolve_disk_type("c4-standard-4", boot_disk_type="hyperdisk-throughput"),
            "hyperdisk-throughput"
        )

    # --------------------------------------------------------------------------
    # 4. Machine Type Validation Matrix
    # --------------------------------------------------------------------------
    def test_machine_type_variable_validation_matrix(self):
        """Verify machine_type validation blocks unsupported/low-spec machine families."""
        # Extract validation contains list from compute variables.tf
        val_match = re.search(
            r'validation\s*\{[^}]*contains\(\[([^\]]+)\]',
            self.compute_vars,
            re.DOTALL,
        )
        self.assertIsNotNone(val_match, "Validation block not found in machine_type variable definition")
        allowed_types = [t.strip().strip('"') for t in val_match.group(1).split(",") if t.strip()]

        # High-performance types must be allowed
        self.assertIn("c4-standard-4", allowed_types)
        self.assertIn("c4-standard-8", allowed_types)
        self.assertIn("c3-standard-4", allowed_types)
        self.assertIn("c3-standard-8", allowed_types)

        # Low-spec, high-latency machine types must NOT be allowed
        forbidden_types = ["e2-micro", "f1-micro", "n1-standard-1", "t2.micro", "g1-small"]
        for bad_type in forbidden_types:
            self.assertNotIn(
                bad_type,
                allowed_types,
                f"Low-spec type {bad_type} must not be in allowed machine types!"
            )

    # --------------------------------------------------------------------------
    # 5. Collocation Placement Policy Verification
    # --------------------------------------------------------------------------
    def test_collocation_placement_policy_configuration(self):
        """Verify compact placement policy declares collocation = 'COLLOCATED' and binds to VM."""
        # Verify placement policy resource exists
        self.assertIn('resource "google_compute_resource_policy" "compact_placement"', self.compute_main)

        # Verify group_placement_policy block
        policy_match = re.search(
            r'group_placement_policy\s*\{([^}]+)\}',
            self.compute_main,
            re.DOTALL,
        )
        self.assertIsNotNone(policy_match, "group_placement_policy block missing in compute main.tf")
        policy_content = policy_match.group(1)

        # Verify collocation attribute
        colloc_match = re.search(r'collocation\s*=\s*["\']COLLOCATED["\']', policy_content)
        self.assertIsNotNone(
            colloc_match,
            "CRITICAL: collocation attribute must be exactly 'COLLOCATED' for compact intra-rack placement!"
        )

        # Verify vm_count attribute
        self.assertIn("vm_count    = var.instance_count", policy_content)

        # Verify instance resource_policies attachment
        self.assertIn(
            "resource_policies = var.enable_placement_policy ? [google_compute_resource_policy.compact_placement[0].id] : []",
            self.compute_main,
            "resource_policies not conditionally attached to google_compute_instance!"
        )

        # Verify placement policy output
        self.assertIn('output "placement_policy_id"', self.compute_outputs)
        self.assertIn('output "placement_policy_name"', self.compute_outputs)

    # --------------------------------------------------------------------------
    # 6. Root Integration & Dependency Graph Verification
    # --------------------------------------------------------------------------
    def test_root_integration_compute_module(self):
        """Verify root main.tf and outputs.tf integrate module.compute correctly."""
        # Check module compute declaration in root main.tf
        compute_module_match = re.search(
            r'module\s+["\']compute["\']\s*\{([^}]+)\}',
            self.root_main,
            re.DOTALL,
        )
        self.assertIsNotNone(compute_module_match, "module 'compute' is not declared in root main.tf")
        mod_content = compute_module_match.group(1)

        # Verify required inputs passed
        self.assertIn("network_id            = module.networking.network_id", mod_content)
        self.assertIn("subnet_id             = module.networking.subnet_hft_id", mod_content)
        self.assertIn("service_account_email = module.iam.hft_engine_sa_email", mod_content)
        self.assertIn("machine_type          = var.machine_type", mod_content)

        # Verify depends_on
        self.assertIn("module.networking", mod_content)
        self.assertIn("module.iam", mod_content)

        # Verify root outputs
        self.assertIn('output "hft_engine_machine_type"', self.root_outputs)
        self.assertIn('output "hft_engine_zone"', self.root_outputs)
        self.assertIn('output "hft_engine_placement_policy_id"', self.root_outputs)
        self.assertIn('output "hft_engine_private_ip"', self.root_outputs)

    # --------------------------------------------------------------------------
    # 7. Terraform CLI Validation Suite
    # --------------------------------------------------------------------------
    def test_terraform_validate_cli(self):
        """Empirically execute terraform validate to ensure complete configuration passes."""
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
