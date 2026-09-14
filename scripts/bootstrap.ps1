<#
.SYNOPSIS
    Bootstrap the development environment from a clean checkout.

.DESCRIPTION
    Creates the virtual environment, upgrades pip, and installs the pinned
    development toolchain.

    Two environment characteristics are accounted for:

    1. Intermittent read timeouts against pypi.org have been observed on
       the development machine used for this project. Elevated timeout and
       retry settings are used to keep bootstrap deterministic under those
       conditions. Without them, pip can report a misleading "Could not find
       a version that satisfies the requirement" error whose real cause is
       a network timeout.

    2. In some regions (notably Iran), the /simple/ index endpoint of
       pypi.org is filtered at the provider level for some packages while
       the JSON metadata API is not. The -IndexUrl parameter allows the
       bootstrap to point at an alternative index. A known-working mirror
       in this situation is:

           -IndexUrl "https://mirror-pypi.runflare.com/simple"

.PARAMETER Recreate
    If set, deletes the existing .venv directory before recreating it.

.PARAMETER IndexUrl
    Alternate pip index URL. When set, pip will use it for the pip upgrade
    and for installing requirements. The host is added to pip's trusted
    hosts so that TLS-terminating mirrors work without extra configuration.

.EXAMPLE
    .\scripts\bootstrap.ps1

.EXAMPLE
    .\scripts\bootstrap.ps1 -Recreate

.EXAMPLE
    .\scripts\bootstrap.ps1 -IndexUrl "https://mirror-pypi.runflare.com/simple"
#>
[CmdletBinding()]
param(
    [switch]$Recreate,
    [string]$IndexUrl = ""
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

# Build the argument array for pip. When -IndexUrl is supplied, the index
# and trusted host are added; otherwise pip uses its configured defaults.
$pipIndexArgs = @()
if ($IndexUrl) {
    $pipIndexArgs = @("--index-url", $IndexUrl)
    try {
        $host_ = ([Uri]$IndexUrl).Host
        if ($host_) { $pipIndexArgs += @("--trusted-host", $host_) }
    } catch {
        Write-Warning "Could not parse -IndexUrl as a URI; proceeding without --trusted-host."
    }
    Write-Host "Using alternate index: $IndexUrl"
}

Write-Host "Upgrading pip ..."
& $python -m pip install --upgrade pip --timeout 120 --retries 10 @pipIndexArgs

Write-Host "Installing development requirements ..."
& $python -m pip install `
    --timeout 120 `
    --retries 10 `
    @pipIndexArgs `
    -r (Join-Path $repoRoot "requirements-dev.txt")

Write-Host ""
Write-Host "Toolchain installed:"
& $python --version
& $python -m pip --version
& $python -m pytest --version
& $python -m ruff --version
& $python -m mypy --version
