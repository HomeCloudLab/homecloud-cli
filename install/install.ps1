# HomeCloud CLI installer for Windows (amd64).
# Usage: irm https://install.homecloud.dev/windows | iex
$ErrorActionPreference = "Stop"

$InstallBase = if ($env:HOMECLOUD_INSTALL_URL) { $env:HOMECLOUD_INSTALL_URL } else { "https://cli.homecloud.dev/releases" }
$Version = if ($env:HOMECLOUD_VERSION) { $env:HOMECLOUD_VERSION } else { "latest" }
$InstallDir = if ($env:HOMECLOUD_INSTALL_DIR) { $env:HOMECLOUD_INSTALL_DIR } else { "$env:LOCALAPPDATA\Programs\homecloud" }
$Artifact = "homecloud-windows-amd64.exe"
$Url = "$InstallBase/$Version/$Artifact"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Dest = Join-Path $InstallDir "homecloud.exe"

Write-Host "Installing HomeCloud CLI ($Version, windows-amd64)..."
Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
    $env:Path = "$env:Path;$InstallDir"
}

Write-Host "Installed: $Dest"
& $Dest version
