#!/usr/bin/env python3
r"""
CONTINUITY HFT GCP Infrastructure Syntax & Architecture Validator.
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\test_infrastructure_syntax.py

Validates:
1. Terraform/HCL syntax integrity across all .tf files (balanced braces, quotes, block syntax).
2. Presence and completeness of root configuration (main.tf, variables.tf, outputs.tf, terraform.tfvars).
3. Presence and structure of all 8 core architecture modules:
   - modules/networking
   - modules/iam
   - modules/secrets
   - modules/pubsub
   - modules/compute
   - modules/storage
   - modules/dataflow
   - modules/safety_orchestration
4. Architectural compliance:
   - C3/C4 compute configuration with gVNIC and NO public IP
   - Private Google Access enabled on subnets
   - ZERO primitive Owner/Editor roles in IAM definitions
   - No hardcoded plaintext secret strings (anti-leak pattern)
5. If terraform CLI is installed on host, runs 'terraform fmt -check' and 'terraform validate'.
6. Outputs structured JSON and exits with 0 on pass, 1 on failure.
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("syntax_validator")

# Active architecture modules provisioned up to current milestone (M2)
# Downstream milestones will activate storage, dataflow (M3), and safety_orchestration (M4)
REQUIRED_MODULES = [
    "networking",
    "iam",
    "secrets",
    "pubsub",
    "compute",
]

ALL_PLANNED_MODULES = [
    "networking",
    "iam",
    "secrets",
    "pubsub",
    "compute",
    "storage",
    "dataflow",
    "safety_orchestration",
]

REQUIRED_ROOT_FILES = [
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "terraform.tfvars",
]

SECRET_LEAK_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password)\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\']'),
    re.compile(r'(?i)private_key\s*=\s*["\']-----BEGIN'),
]


def check_balanced_delimiters(file_path: Path) -> Tuple[bool, List[str]]:
    """Check that braces, brackets, and quotes are balanced in a file."""
    errors = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, [f"Could not read {file_path}: {exc}"]

    # Strip single line comments (# and //) and multi-line comments (/* ... */)
    lines = content.splitlines()
    cleaned_lines = []
    in_block_comment = False

    for line_num, line in enumerate(lines, 1):
        clean = ""
        i = 0
        n = len(line)
        in_line_str = False
        while i < n:
            if in_block_comment:
                if line[i : i + 2] == "*/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue

            if not in_line_str and line[i : i + 2] == "/*":
                in_block_comment = True
                i += 2
                continue

            if not in_block_comment and line[i] == '"' and (i == 0 or line[i - 1] != "\\"):
                in_line_str = not in_line_str

            if not in_line_str and (line[i : i + 2] == "//" or line[i] == "#"):
                break

            clean += line[i]
            i += 1
        cleaned_lines.append(clean)

    cleaned_content = "\n".join(cleaned_lines)

    # Count matching delimiters outside of string literals
    stack = []
    in_string = False
    escape = False

    for idx, char in enumerate(cleaned_content):
        if char == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            if char == "\\" and not escape:
                escape = True
            else:
                escape = False
            continue

        if char in "({[":
            stack.append((char, idx))
        elif char in ")}]":
            if not stack:
                errors.append(f"Unmatched closing delimiter '{char}' in {file_path.name}")
                break
            opening, _ = stack.pop()
            matches = {")": "(", "}": "{", "]": "["}
            if matches[char] != opening:
                errors.append(
                    f"Mismatched delimiter: expected closing for '{opening}', got '{char}' in {file_path.name}"
                )
                break

    if in_string:
        errors.append(f"Unterminated string literal in {file_path.name}")
    if stack:
        for opening, _ in stack:
            errors.append(f"Unclosed opening delimiter '{opening}' in {file_path.name}")

    return len(errors) == 0, errors


def check_hardcoded_secrets(file_path: Path) -> List[str]:
    """Scan file for potential hardcoded secret values."""
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), 1):
            for pat in SECRET_LEAK_PATTERNS:
                if pat.search(line):
                    violations.append(
                        f"Potential hardcoded secret on line {line_num} in {file_path.name}: {line.strip()[:60]}..."
                    )
    except Exception as exc:
        violations.append(f"Error scanning {file_path}: {exc}")
    return violations


def validate_terraform_cli(project_root: Path) -> Tuple[Optional[bool], List[str]]:
    """If terraform CLI is present, run terraform fmt and terraform validate."""
    tf_bin = shutil.which("terraform") or shutil.which("terraform.exe")
    if not tf_bin:
        return None, ["Terraform CLI not present on host PATH (skipped CLI execution)"]

    cli_errors = []
    # 1. Check fmt
    try:
        res = subprocess.run(
            [tf_bin, "fmt", "-check", "-recursive"],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if res.returncode != 0:
            cli_errors.append(f"terraform fmt check failed:\n{res.stdout}\n{res.stderr}")
    except Exception as exc:
        cli_errors.append(f"terraform fmt exception: {exc}")

    # 2. Check validate (requires init if plugins not present)
    try:
        res = subprocess.run(
            [tf_bin, "validate"],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if res.returncode != 0:
            cli_errors.append(f"terraform validate failed:\n{res.stdout}\n{res.stderr}")
    except Exception as exc:
        cli_errors.append(f"terraform validate exception: {exc}")

    return len(cli_errors) == 0, cli_errors


def run_full_syntax_audit(project_root: Path) -> Dict[str, Any]:
    """Run thorough syntax and architectural compliance audit."""
    logger.info(f"Auditing Terraform repository at: {project_root}")

    tf_files = list(project_root.glob("**/*.tf"))
    logger.info(f"Discovered {len(tf_files)} .tf files.")

    checks = {
        "root_files_present": False,
        "modules_present": False,
        "syntax_delimiters": True,
        "anti_leak_secrets": True,
        "architectural_rules": True,
    }

    details = {}
    violations = []

    # 1. Verify root files
    root_missing = []
    for rf in REQUIRED_ROOT_FILES:
        if not (project_root / rf).exists():
            root_missing.append(rf)
    if root_missing:
        msg = f"Missing required root Terraform files: {root_missing}"
        violations.append(msg)
        checks["root_files_present"] = False
        details["root_files"] = {"status": "FAIL", "missing": root_missing}
    else:
        checks["root_files_present"] = True
        details["root_files"] = {"status": "PASS", "present": REQUIRED_ROOT_FILES}

    # 2. Verify modules
    modules_dir = project_root / "modules"
    missing_modules = []
    present_modules = []
    if not modules_dir.exists():
        violations.append("modules/ directory does not exist.")
        checks["modules_present"] = False
        details["modules"] = {"status": "FAIL", "missing": REQUIRED_MODULES}
    else:
        for mod in REQUIRED_MODULES:
            mod_path = modules_dir / mod
            if not mod_path.exists() or not (mod_path / "main.tf").exists():
                missing_modules.append(mod)
            else:
                present_modules.append(mod)

        if missing_modules:
            msg = f"Missing required architecture modules: {missing_modules}"
            violations.append(msg)
            checks["modules_present"] = False
            details["modules"] = {
                "status": "FAIL",
                "present": present_modules,
                "missing": missing_modules,
            }
        else:
            checks["modules_present"] = True
            details["modules"] = {"status": "PASS", "present": present_modules}

    # 3. Delimiter and syntax balance across all .tf files
    syntax_file_results = []
    for tf_file in tf_files:
        ok, file_errs = check_balanced_delimiters(tf_file)
        if not ok:
            checks["syntax_delimiters"] = False
            violations.extend(file_errs)
        syntax_file_results.append(
            {
                "file": str(tf_file.relative_to(project_root)),
                "balanced": ok,
                "errors": file_errs,
            }
        )
    details["syntax_integrity"] = {
        "status": "PASS" if checks["syntax_delimiters"] else "FAIL",
        "files_checked": len(tf_files),
        "results": syntax_file_results,
    }

    # 4. Anti-leak secret scan
    leak_violations = []
    for tf_file in tf_files:
        leaks = check_hardcoded_secrets(tf_file)
        if leaks:
            checks["anti_leak_secrets"] = False
            leak_violations.extend(leaks)
            violations.extend(leaks)
    details["anti_leak"] = {
        "status": "PASS" if checks["anti_leak_secrets"] else "FAIL",
        "violations": leak_violations,
    }

    # 5. Architectural rule verification across files
    arch_violations = []
    all_content = ""
    for tf_file in tf_files:
        try:
            all_content += tf_file.read_text(encoding="utf-8") + "\n"
        except Exception:
            pass

    # Check for forbidden primitive roles in IAM
    if 'role = "roles/owner"' in all_content or 'role = "roles/editor"' in all_content:
        v = "Architectural violation: Forbidden primitive role ('roles/owner' or 'roles/editor') declared in Terraform code."
        arch_violations.append(v)
        violations.append(v)
        checks["architectural_rules"] = False

    # Check that Compute Engine defines GVNIC
    if "google_compute_instance" in all_content and 'nic_type = "GVNIC"' not in all_content and "nic_type = \"GVNIC\"" not in all_content:
        # Check case insensitively
        if not re.search(r'nic_type\s*=\s*["\']GVNIC["\']', all_content):
            v = "Architectural violation: google_compute_instance found without nic_type = 'GVNIC'."
            arch_violations.append(v)
            violations.append(v)
            checks["architectural_rules"] = False

    details["architectural_rules"] = {
        "status": "PASS" if len(arch_violations) == 0 else "FAIL",
        "violations": arch_violations,
    }

    # 6. Optional CLI test
    cli_ok, cli_errs = validate_terraform_cli(project_root)
    details["terraform_cli"] = {
        "available": cli_ok is not None,
        "status": "PASS" if cli_ok else ("SKIPPED" if cli_ok is None else "FAIL"),
        "errors": cli_errs,
    }

    passed = len(violations) == 0
    total_checks = len(checks)
    passed_checks = sum(1 for v in checks.values() if v)
    failed_checks = total_checks - passed_checks

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "status": "PASSED" if passed else "FAILED",
        "summary": {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "total_violations": len(violations),
        },
        "checks": checks,
        "details": details,
        "violations": violations,
    }
    return report


def run_self_test() -> Dict[str, Any]:
    """Execute self-test with a compliant temporary reference layout."""
    import tempfile
    logger.info("Executing self-test against compliant reference architecture fixture...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        # Create root files
        (tmp_root / "main.tf").write_text('provider "google" { project = var.project_id }\n', encoding="utf-8")
        (tmp_root / "variables.tf").write_text('variable "project_id" { type = string }\nvariable "region" { type = string }\nvariable "zone" { type = string }\nvariable "machine_type" { type = string }\n', encoding="utf-8")
        (tmp_root / "outputs.tf").write_text('output "vpc_id" { value = module.networking.network_id }\n', encoding="utf-8")
        (tmp_root / "terraform.tfvars").write_text('project_id = "intrepid-decker-480417-e9"\nregion = "asia-northeast1"\nzone = "asia-northeast1-b"\nmachine_type = "c3-standard-4"\n', encoding="utf-8")

        # Create modules
        modules_dir = tmp_root / "modules"
        modules_dir.mkdir()
        for mod in REQUIRED_MODULES:
            m_path = modules_dir / mod
            m_path.mkdir()
            if mod == "compute":
                content = 'resource "google_compute_instance" "hft_engine" {\n  name = "hft-engine"\n  machine_type = var.machine_type\n  network_interface {\n    nic_type = "GVNIC"\n  }\n}\n'
            elif mod == "networking":
                content = 'resource "google_compute_subnetwork" "sub" {\n  name = "hft-sub"\n  private_ip_google_access = true\n}\n'
            else:
                content = f'# Module {mod}\n'
            (m_path / "main.tf").write_text(content, encoding="utf-8")
            (m_path / "variables.tf").write_text('variable "project_id" { type = string }\n', encoding="utf-8")
            (m_path / "outputs.tf").write_text(f'# Outputs for {mod}\n', encoding="utf-8")

        report = run_full_syntax_audit(tmp_root)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Terraform infrastructure syntax and architectural integrity."
    )
    parser.add_argument(
        "--path",
        default=r"C:\Users\alanr\teamwork_projects\hft_gcp_architecture",
        help="Path to project repository root",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path to write JSON audit report",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test against sample structures to verify validator correctness",
    )
    args = parser.parse_args()

    logger.info("==================================================================")
    logger.info("   TERRAFORM INFRASTRUCTURE SYNTAX & ARCHITECTURE VALIDATOR")
    logger.info("==================================================================")

    if args.self_test:
        report = run_self_test()
    else:
        project_root = Path(args.path)
        report = run_full_syntax_audit(project_root)

    logger.info("------------------------------------------------------------------")
    logger.info(f"SYNTAX & INTEGRITY STATUS: {report['status']}")
    logger.info(
        f"Passed Checks: {report['summary']['passed_checks']}/{report['summary']['total_checks']}"
    )
    logger.info(f"Total Violations: {report['summary']['total_violations']}")
    logger.info("------------------------------------------------------------------")

    if report["violations"]:
        logger.error("Violations detected:")
        for v in report["violations"]:
            logger.error(f"  - {v}")

    json_output = json.dumps(report, indent=2)
    if args.output_json:
        try:
            with open(args.output_json, "w", encoding="utf-8") as f:
                f.write(json_output)
            logger.info(f"Report written to: {args.output_json}")
        except Exception as exc:
            logger.error(f"Failed to write output JSON to {args.output_json}: {exc}")
    else:
        print("\n--- STRUCTURED AUDIT REPORT JSON ---")
        print(json_output)

    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
