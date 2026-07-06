# Build single-file homecloud binary on Windows (amd64).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SdkRoot = if ($env:HOMECLOUD_SDK_ROOT) { $env:HOMECLOUD_SDK_ROOT } else { Join-Path (Split-Path $Root -Parent) "homecloud-sdk" }
$Dist = Join-Path $Root "dist"
$Version = (Get-Content (Join-Path $Root "homecloud_cli\__init__.py") | Select-String '__version__ = "(.+)"').Matches.Groups[1].Value
$Artifact = "homecloud-windows-amd64.exe"

if (-not (Test-Path (Join-Path $SdkRoot "pyproject.toml"))) {
    throw "homecloud-sdk not found at $SdkRoot"
}

Write-Host "Building $Artifact (v$Version)..."

$env:HOMECLOUD_SDK_ROOT = $SdkRoot
python -m pip install -q -e $SdkRoot -e "${Root}[build]"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Dist "build")
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Dist $Artifact)

pyinstaller --noconfirm --clean --distpath $Dist --workpath (Join-Path $Dist "build") (Join-Path $Root "homecloud.spec")

Move-Item -Force (Join-Path $Dist "homecloud.exe") (Join-Path $Dist $Artifact)

$hash = Get-FileHash (Join-Path $Dist $Artifact) -Algorithm SHA256
"$($hash.Hash.ToLower())  $Artifact" | Set-Content (Join-Path $Dist "$Artifact.sha256")

Write-Host "Built: $(Join-Path $Dist $Artifact)"
