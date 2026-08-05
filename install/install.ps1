# HomeCloud CLI installer for Windows (amd64).
# Usage: irm https://homecloud-cli.so.holab.abrdns.com/install/install.ps1 | iex
$ErrorActionPreference = "Stop"

$InstallBase = if ($env:HOMECLOUD_INSTALL_URL) { $env:HOMECLOUD_INSTALL_URL } else { "https://homecloud-cli.so.holab.abrdns.com/releases" }
$Version = if ($env:HOMECLOUD_VERSION) { $env:HOMECLOUD_VERSION } else { "latest" }
$InstallDir = if ($env:HOMECLOUD_INSTALL_DIR) { $env:HOMECLOUD_INSTALL_DIR } else { "$env:LOCALAPPDATA\Programs\HomeCloud" }
$Artifact = "homecloud-windows-amd64.exe"
$Url = "$InstallBase/$Version/$Artifact"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Dest = Join-Path $InstallDir "homecloud.exe"

Write-Host "Installing HomeCloud CLI ($Version, windows-amd64)..."
Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$legacyDir = "$env:LOCALAPPDATA\Programs\homecloud"
$parts = @()
if ($userPath) {
    $parts = @($userPath -split ";" | Where-Object {
        $_ -and ($_ -ne $InstallDir) -and ($_ -ne $legacyDir)
    })
}
$newPath = (@($InstallDir) + $parts) -join ";"
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
$env:Path = "$InstallDir;$env:Path"

Write-Host "Installed: $Dest"
& $Dest version
