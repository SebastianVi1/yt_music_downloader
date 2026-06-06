#Requires -Version 5.1
<#
.SYNOPSIS
    Windows launcher for YT Music Downloader.
.DESCRIPTION
    Creates a Python virtual environment (if missing), installs
    dependencies, and runs the interactive CLI.
.PARAMETER Install
    Register ytmusic-dl as a command available from any terminal.
.PARAMETER Uninstall
    Remove the ytmusic-dl command from the system PATH.
#>
param(
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptDir ".venv"

# -- platform-aware paths ---------------------------------------------------
if ($IsWindows -or $env:OS -eq "Windows_NT") {
    $VenvScripts = Join-Path $VenvDir "Scripts"
    $PythonExe   = Join-Path $VenvScripts "python.exe"
    $PipExe      = Join-Path $VenvScripts "pip.exe"
}
else {
    $VenvBin    = Join-Path $VenvDir "bin"
    $PythonExe  = Join-Path $VenvBin "python"
    $PipExe     = Join-Path $VenvBin "pip"
}


# ===========================================================================
# Install / uninstall functions  (must precede the dispatch)
# ===========================================================================

function Install-YtmusicDl {
    <#
    .SYNOPSIS
        Create a batch-file wrapper and add its directory to the user
        PATH so ``ytmusic-dl`` works from any terminal.
    #>

    if (-not ($IsWindows -or $env:OS -eq "Windows_NT")) {
        Write-Host "Install mode is only supported on Windows." -ForegroundColor Yellow
        return
    }

    $AppDir = Join-Path $env:APPDATA "ytmusic-dl"
    $BatPath = Join-Path $AppDir "ytmusic-dl.bat"
    $Ps1Path = Join-Path $ScriptDir "run.ps1"

    if (-not (Test-Path -LiteralPath $AppDir)) {
        New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    }

    # Batch-file wrapper that bypasses the PowerShell execution policy
    @"
@echo off
powershell.exe -NoLogo -ExecutionPolicy Bypass -File `"$Ps1Path`" %*
"@ | Set-Content -LiteralPath $BatPath -Encoding ASCII

    Write-Host "Created $BatPath" -ForegroundColor Green

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
    if ($AppDir -notin $currentPath) {
        $newPath = ($currentPath + $AppDir | Where-Object { $_ }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:Path = "$AppDir;$env:Path"

        Write-Host ""
        Write-Host "Added to user PATH: $AppDir" -ForegroundColor Green
        Write-Host ""
        Write-Host "You can now run 'ytmusic-dl' from any terminal." -ForegroundColor Cyan
        Write-Host "If it doesn't work immediately, restart your terminal." -ForegroundColor DarkGray
    }
    else {
        Write-Host "Already on user PATH: $AppDir" -ForegroundColor DarkGray
    }
}

function Uninstall-YtmusicDl {
    <#
    .SYNOPSIS
        Remove the ``ytmusic-dl`` batch wrapper and its directory
        from PATH.
    #>

    $AppDir = Join-Path $env:APPDATA "ytmusic-dl"

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
    if ($AppDir -in $currentPath) {
        $newPath = ($currentPath | Where-Object { $_ -ne $AppDir }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:Path = ($env:Path -split ";" | Where-Object { $_ -ne $AppDir }) -join ";"
        Write-Host "Removed from user PATH: $AppDir" -ForegroundColor Yellow
    }

    if (Test-Path -LiteralPath $AppDir) {
        Remove-Item -LiteralPath $AppDir -Recurse -Force
        Write-Host "Deleted $AppDir" -ForegroundColor Yellow
    }

    Write-Host "ytmusic-dl has been uninstalled." -ForegroundColor Green
}


# ===========================================================================
# Dispatch
# ===========================================================================

if ($Install) {
    Install-YtmusicDl
    exit $LASTEXITCODE
}
if ($Uninstall) {
    Uninstall-YtmusicDl
    exit $LASTEXITCODE
}

# -- create venv if missing -------------------------------------------------
if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    # Prefer 'python' on Windows (python3 is often a Microsoft Store stub);
    # prefer 'python3' on Unix (where 'python' may still be Python 2).
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
    }
    else {
        $pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
    }
    & $pythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    & $PipExe install -r (Join-Path $ScriptDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
        exit 1
    }
}

# -- ffmpeg check -----------------------------------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  ffmpeg is not installed. Please install it:" -ForegroundColor Yellow
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Write-Host "    winget install Gyan.FFmpeg" -ForegroundColor DarkGray
    }
    else {
        Write-Host "    sudo apt install ffmpeg" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# -- launch -----------------------------------------------------------------
& $PythonExe (Join-Path $ScriptDir "main.py")
