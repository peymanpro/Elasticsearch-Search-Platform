<#
.SYNOPSIS
    Bootstrap the development environment from a clean checkout.

.DESCRIPTION
    Creates the virtual environment, upgrades pip, and installs the pinned
    development toolchain.

    The elevated timeout and retry settings are required because the
    environment used to develop this project has been observed to experience
    intermittent read timeouts against pypi.org. Without these settings,
    pip can report a misleading "Could not find a version that satisfies
    the requirement" error when the real cause is a network timeout.

.PARAMETER Recreate
    If set, deletes the existing .venv directory before recreating it.

.EXAMPLE
    .\scripts\bootstrap.ps1
    .\scripts\bootstrap.ps1 -Recreate
#>
[CmdletBinding()]
param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPath = Join-Path $repoRoot ".venv"
$python   = Join-Path $venvPath "Scripts\python.exe"

if ($Recreate -and (Test-Path $venvPath)) {
    Write-Host "Removing existing .venv ..."
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment at .venv ..."
    python -m venv .venv
}

Write-Host "Upgrading pip ..."
& $python -m pip install --upgrade pip --timeout 120 --retries 10

Write-Host "Installing development requirements ..."
& $python -m pip install `
    --timeout 120 `
    --retries 10 `
    -r (Join-Path $repoRoot "requirements-dev.txt")

Write-Host ""
Write-Host "Toolchain installed:"
& $python --version
& $python -m pip --version
& $python -m pytest --version
& $python -m ruff --version
& $python -m mypy --version
