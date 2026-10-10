"""
Adversarial Live Audit & Security Verification Suite
Target: C:\\Users\\alanr\\teamwork_projects\\hft_gcp_architecture\\tests\\test_adversarial_live_audit.py

Executes empirical tests directly against live Google Cloud Platform resources
in project 'intrepid-decker-480417-e9' (region: 'asia-northeast1') to challenge:
- Compute network isolation (0 public IPs, 0 accessConfigs)
- Subnet security (Private Google Access enabled)
- IAM least-privilege (0 primitive Owner/Editor roles on 5 HFT SAs)
- Ingress perimeter (0.0.0.0/0 ingress denied)
- Bigtable SSD storage type
- Memorystore Redis Standard HA tier and AUTH
- Dataflow streaming job active status
- Emergency Shutdown Function ingress isolation and EventArc trigger wiring
"""

import json
import shutil
import subprocess
import unittest


def run_gcloud_json(cmd_str: str):
    """Execute a gcloud command returning parsed JSON output."""
    proc = subprocess.run(
        cmd_str,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed (code {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)


class TestAdversarialLiveGcpPerimeter(unittest.TestCase):
    PROJECT_ID = "intrepid-decker-480417-e9"
    REGION = "asia-northeast1"
    VPC_NAME = "hft-primary-vpc"

    HFT_SERVICE_ACCOUNTS = [
        "sa-hft-engine@intrepid-decker-480417-e9.iam.gserviceaccount.com",
        "sa-dataflow-worker@intrepid-decker-480417-e9.iam.gserviceaccount.com",
        "sa-hft-eventarc@intrepid-decker-480417-e9.iam.gserviceaccount.com",
        "sa-emergency-shutdown@intrepid-decker-480417-e9.iam.gserviceaccount.com",
        "sa-cicd-deployer@intrepid-decker-480417-e9.iam.gserviceaccount.com",
    ]

    def test_live_compute_zero_access_config_in_hft_vpc(self):
        """Verify that NO Compute VM in hft-primary-vpc has accessConfigs or public IPs."""
        instances = run_gcloud_json(
            f"gcloud compute instances list --project={self.PROJECT_ID} --format=json"
        )
        hft_vms = [
            inst
            for inst in instances
            if any(
                self.VPC_NAME in nic.get("network", "")
                for nic in inst.get("networkInterfaces", [])
            )
        ]
        self.assertGreaterEqual(
            len(hft_vms),
            1,
            f"Expected at least 1 VM in {self.VPC_NAME}, found {len(hft_vms)}",
        )

        for vm in hft_vms:
            vm_name = vm.get("name")
            for nic in vm.get("networkInterfaces", []):
                access_configs = nic.get("accessConfigs", [])
                self.assertEqual(
                    len(access_configs),
                    0,
                    f"VIOLATION: VM '{vm_name}' has accessConfig: {access_configs}",
                )
                # Confirm internal IP only
                internal_ip = nic.get("networkIP", "")
                self.assertTrue(
                    internal_ip.startswith("10.10."),
                    f"VM '{vm_name}' has non-private IP: {internal_ip}",
                )

    def test_live_subnets_private_google_access(self):
        """Verify that ALL subnets in hft-primary-vpc have Private Google Access enabled."""
        subnets = run_gcloud_json(
            f"gcloud compute networks subnets list --project={self.PROJECT_ID} --network={self.VPC_NAME} --format=json"
        )
        self.assertGreaterEqual(
            len(subnets),
            2,
            f"Expected at least 2 subnets in {self.VPC_NAME}, found {len(subnets)}",
        )

        for sub in subnets:
            sub_name = sub.get("name")
            pga = sub.get("privateIpGoogleAccess")
            self.assertTrue(
                pga is True,
                f"VIOLATION: Subnet '{sub_name}' in {self.VPC_NAME} has Private Google Access = {pga}",
            )

    def test_live_iam_zero_primitive_roles_on_5_hft_sas(self):
        """Verify zero primitive Owner/Editor roles for all 5 HFT service accounts."""
        policy = run_gcloud_json(
            f"gcloud projects get-iam-policy {self.PROJECT_ID} --format=json"
        )
        primitive_roles = {"roles/owner", "roles/editor", "roles/viewer"}
        violations = []

        for binding in policy.get("bindings", []):
            role = binding.get("role", "")
            members = binding.get("members", [])
            if role in primitive_roles:
                for member in members:
                    for sa in self.HFT_SERVICE_ACCOUNTS:
                        if member == f"serviceAccount:{sa}":
                            violations.append((sa, role))

        self.assertEqual(
            violations,
            [],
            f"VIOLATION: Found primitive role bindings for HFT service accounts: {violations}",
        )

    def test_live_firewall_no_public_ingress(self):
        """Verify that firewall rules in hft-primary-vpc do not allow open 0.0.0.0/0 ingress."""
        fw_rules = run_gcloud_json(
            f'gcloud compute firewall-rules list --project={self.PROJECT_ID} --filter="network:{self.VPC_NAME}" --format=json'
        )
        for rule in fw_rules:
            if rule.get("direction") == "INGRESS":
                source_ranges = rule.get("sourceRanges", [])
                if "0.0.0.0/0" in source_ranges:
                    # Must be a DENY rule or contain no allowed protocols
                    self.assertIsNone(
                        rule.get("allowed"),
                        f"VIOLATION: Firewall rule '{rule.get('name')}' allows ingress from 0.0.0.0/0",
                    )

    def test_live_bigtable_ssd_enforcement(self):
        """Verify Bigtable cluster uses SSD in asia-northeast1."""
        clusters = run_gcloud_json(
            f"gcloud bigtable clusters list --instances=hft-tick-store --project={self.PROJECT_ID} --format=json"
        )
        self.assertGreaterEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(
            cluster.get("defaultStorageType"),
            "SSD",
            f"VIOLATION: Bigtable cluster storage type is {cluster.get('defaultStorageType')}, expected SSD",
        )
        self.assertIn("asia-northeast1", cluster.get("location", ""))

    def test_live_memorystore_redis_ha_and_auth(self):
        """Verify Memorystore Redis is Standard HA with AUTH enabled and PSA connect mode."""
        redis = run_gcloud_json(
            f"gcloud redis instances describe hft-redis-cache --region={self.REGION} --project={self.PROJECT_ID} --format=json"
        )
        self.assertEqual(redis.get("tier"), "STANDARD_HA")
        self.assertTrue(redis.get("authEnabled"))
        self.assertEqual(redis.get("connectMode"), "PRIVATE_SERVICE_ACCESS")
        self.assertEqual(redis.get("state"), "READY")

    def test_live_dataflow_streaming_job_running(self):
        """Verify Dataflow streaming job is running in asia-northeast1."""
        jobs = run_gcloud_json(
            f"gcloud dataflow jobs list --region={self.REGION} --project={self.PROJECT_ID} --format=json"
        )
        hft_jobs = [j for j in jobs if "hft-stream-trades" in j.get("name", "")]
        self.assertGreaterEqual(len(hft_jobs), 1)
        job = hft_jobs[0]
        self.assertIn(job.get("state"), ["Running", "JOB_STATE_RUNNING"])

    def test_live_emergency_shutdown_function_internal_only(self):
        """Verify Emergency Shutdown Cloud Function is configured for internal-only ingress."""
        fn = run_gcloud_json(
            f"gcloud functions describe hft-emergency-shutdown --gen2 --region={self.REGION} --project={self.PROJECT_ID} --format=json"
        )
        service_cfg = fn.get("serviceConfig", {})
        self.assertEqual(
            service_cfg.get("ingressSettings"),
            "ALLOW_INTERNAL_ONLY",
            "VIOLATION: Cloud Function ingress is not ALLOW_INTERNAL_ONLY",
        )
        self.assertEqual(fn.get("state"), "ACTIVE")


if __name__ == "__main__":
    unittest.main()
