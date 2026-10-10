# scripts/install_terraform.ps1
# Automated Terraform CLI Installer for Windows Host
# Provides dual-path installation: winget or zero-elevation direct binary download

[CmdletBinding()]
param(
    [string]$InstallDir = "$HOME\.local\bin",
    [string]$PinnedVersion = "1.16.5",
    [switch]$ForceDownload
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    HFT GCP Architecture: Terraform CLI Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check if Terraform is already functional in PATH
$existingTf = Get-Command terraform -ErrorAction SilentlyContinue
if ($existingTf -and -not $ForceDownload) {
    Write-Host "[OK] Terraform is already installed at: $($existingTf.Source)" -ForegroundColor Green
    & terraform version
    exit 0
}

Write-Host "[INFO] Terraform not found in PATH. Initiating setup..." -ForegroundColor Yellow

# Ensure destination bin directory exists
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Host "[INFO] Created local bin directory: $InstallDir" -ForegroundColor Gray
}

$installedViaWinget = $false

# 2. Attempt winget if available and not forced to direct download
if (-not $ForceDownload -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "[INFO] Attempting installation via winget (HashiCorp.Terraform)..." -ForegroundColor Cyan
    try {
        $proc = Start-Process winget -ArgumentList "install --id HashiCorp.Terraform -e --silent --accept-package-agreements --accept-source-agreements" -NoNewWindow -Wait -PassThru
        if ($proc.ExitCode -eq 0) {
            Write-Host "[OK] winget installation succeeded." -ForegroundColor Green
            $installedViaWinget = $true
        } else {
            Write-Warning "winget exited with code $($proc.ExitCode). Falling back to direct binary download."
        }
    } catch {
        Write-Warning "winget execution failed: $_. Falling back to direct binary download."
    }
}

# 3. Direct binary download fallback (guaranteed to work with zero elevation)
if (-not $installedViaWinget) {
    Write-Host "[INFO] Fetching standalone zip from HashiCorp releases..." -ForegroundColor Cyan

    $targetVersion = $PinnedVersion
    try {
        $checkpoint = Invoke-RestMethod -Uri "https://checkpoint-api.hashicorp.com/v1/check/terraform" -TimeoutSec 5 -ErrorAction Stop
        if ($checkpoint.current_version) {
            $targetVersion = $checkpoint.current_version
        }
    } catch {
        Write-Host "[INFO] Checkpoint API unreachable, using pinned version $PinnedVersion" -ForegroundColor Gray
    }

    $zipUrl = "https://releases.hashicorp.com/terraform/${targetVersion}/terraform_${targetVersion}_windows_amd64.zip"
    $tempZip = Join-Path $env:TEMP "terraform_${targetVersion}_windows_amd64.zip"

    Write-Host "[INFO] Downloading $zipUrl..." -ForegroundColor Gray
    curl.exe -L -s -o "$tempZip" "$zipUrl"

    if (-not (Test-Path $tempZip) -or (Get-Item $tempZip).Length -lt 10000000) {
        throw "Download failed or corrupted zip file at $tempZip"
    }

    Write-Host "[INFO] Extracting terraform.exe to $InstallDir..." -ForegroundColor Gray
    Expand-Archive -Path $tempZip -DestinationPath $InstallDir -Force
    Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue

    Write-Host "[OK] Extracted terraform.exe into $InstallDir" -ForegroundColor Green
}

# 4. Permanently ensure directory is in user PATH and current session
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    Write-Host "[INFO] Appending $InstallDir to User Environment PATH..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
}

if ($env:PATH -notlike "*$InstallDir*") {
    $env:PATH = "$InstallDir;$env:PATH"
}

# 5. Verification
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    Verifying Terraform CLI" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$tfCmd = Get-Command terraform -ErrorAction SilentlyContinue
if ($tfCmd) {
    Write-Host "[SUCCESS] Terraform is ready:" -ForegroundColor Green
    & terraform version
} elseif (Test-Path "$InstallDir\terraform.exe") {
    Write-Host "[SUCCESS] Terraform binary verified at $InstallDir\terraform.exe:" -ForegroundColor Green
    & "$InstallDir\terraform.exe" version
} else {
    throw "Terraform verification failed. Binary not found."
}
