<#
.SYNOPSIS
    Automated Terraform Infrastructure Syntax and Validation Script.
    Location: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\validate_terraform.ps1

.DESCRIPTION
    Executes comprehensive validation of the HFT GCP Terraform architecture:
    1. Checks for Terraform CLI binary.
    2. Runs 'terraform fmt -check -diff' for formatting compliance.
    3. Runs 'terraform init -backend=false' for provider syntax resolution.
    4. Runs 'terraform validate' for HCL schema validation.
    5. Falls back to native Python syntax & architectural rule validator (test_infrastructure_syntax.py).
    6. Returns exit code 0 on pass, exit code 1 on error.
#>

[CmdletBinding()]
param (
    [string]$ProjectPath = "C:\Users\alanr\teamwork_projects\hft_gcp_architecture",
    [switch]$SkipInit = $false,
    [switch]$SkipPlan = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   CONTINUITY HFT GCP - TERRAFORM AUTOMATED VALIDATOR (PS1)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Target Project Path: $ProjectPath" -ForegroundColor Gray

if (-not (Test-Path $ProjectPath)) {
    Write-Host "[ERROR] Target project path does not exist: $ProjectPath" -ForegroundColor Red
    exit 1
}

# Locate Terraform Binary
$TerraformCmd = Get-Command terraform -ErrorAction SilentlyContinue
$TerraformBin = if ($TerraformCmd) { $TerraformCmd.Source } else { $null }

if (-not $TerraformBin) {
    # Check common alternate directories
    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Terraform\terraform.exe",
        "$env:USERPROFILE\bin\terraform.exe",
        "C:\ProgramData\chocolatey\bin\terraform.exe",
        "C:\tools\terraform.exe"
    )
    foreach ($cand in $Candidates) {
        if (Test-Path $cand) {
            $TerraformBin = $cand
            break
        }
    }
}

$AllPassed = $true

if ($TerraformBin) {
    Write-Host "[INFO] Detected Terraform executable: $TerraformBin" -ForegroundColor Green
    & $TerraformBin -version
    Write-Host ""

    # 1. Formatting Check
    Write-Host "[STEP 1/3] Running 'terraform fmt -check -diff'..." -ForegroundColor Yellow
    Push-Location $ProjectPath
    try {
        & $TerraformBin fmt -check -diff -recursive
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[PASS] All Terraform files are properly formatted." -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Some files need formatting. Run 'terraform fmt -recursive'." -ForegroundColor Red
            $AllPassed = $false
        }

        # 2. Terraform Init (local backend verification)
        if (-not $SkipInit) {
            Write-Host "`n[STEP 2/3] Running 'terraform init -backend=false'..." -ForegroundColor Yellow
            & $TerraformBin init -backend=false
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[PASS] Terraform providers and modules successfully initialized." -ForegroundColor Green
            } else {
                Write-Host "[FAIL] Terraform initialization encountered errors." -ForegroundColor Red
                $AllPassed = $false
            }
        }

        # 3. Terraform Validate
        Write-Host "`n[STEP 3/3] Running 'terraform validate'..." -ForegroundColor Yellow
        & $TerraformBin validate
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[PASS] Terraform configuration is syntactically valid." -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Terraform validation returned schema errors." -ForegroundColor Red
            $AllPassed = $false
        }
    }
    finally {
        Pop-Location
    }
} else {
    Write-Host "[WARNING] Terraform binary not found on system PATH." -ForegroundColor Yellow
    Write-Host "[INFO] To install Terraform on Windows: winget install HashiCorp.Terraform" -ForegroundColor Gray
    Write-Host "[INFO] Executing comprehensive Python AST / Syntax Validator fallback..." -ForegroundColor Cyan

    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $PythonBin = if ($PythonCmd) { $PythonCmd.Source } else { "python" }

    $SyntaxScript = Join-Path $ProjectPath "scripts\test_infrastructure_syntax.py"
    if (Test-Path $SyntaxScript) {
        & $PythonBin $SyntaxScript --path $ProjectPath
        if ($LASTEXITCODE -ne 0) {
            $AllPassed = $false
        }
    } else {
        Write-Host "[ERROR] Could not find syntax validator at $SyntaxScript" -ForegroundColor Red
        $AllPassed = $false
    }
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
if ($AllPassed) {
    Write-Host "   RESULT: ALL INFRASTRUCTURE VALIDATION CHECKS PASSED [OK]" -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "   RESULT: INFRASTRUCTURE VALIDATION FAILED WITH ERRORS [FAIL]" -ForegroundColor Red
    Write-Host "==================================================================" -ForegroundColor Cyan
    exit 1
}
