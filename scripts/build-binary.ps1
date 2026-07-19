# Build single-file homecloud binary on Windows (amd64).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dist = Join-Path $Root "dist"
$Version = (Get-Content (Join-Path $Root "homecloud_cli\__init__.py") | Select-String '__version__ = "(.+)"').Matches.Groups[1].Value
$Artifact = "homecloud-windows-amd64.exe"

$SdkRoot = $env:HOMECLOUD_SDK_ROOT
if (-not $SdkRoot) {
    $sibling = Join-Path (Split-Path -Parent $Root) "homecloud-sdk"
    if (Test-Path (Join-Path $sibling "pyproject.toml")) {
        $SdkRoot = $sibling
    }
}
if (-not $SdkRoot) {
    $ciPath = Join-Path $Root "_homecloud-sdk"
    if (Test-Path (Join-Path $ciPath "pyproject.toml")) {
        $SdkRoot = $ciPath
    }
}

if ($SdkRoot) {
    Write-Host "Installing SDK from $SdkRoot..."
    python -m pip install -q -e $SdkRoot
} else {
    python -c "import homecloud_sdk" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "homecloud-sdk not found. Set HOMECLOUD_SDK_ROOT or place ../homecloud-sdk next to this repo."
    }
}

Write-Host "Building $Artifact (v$Version)..."

if ($SdkRoot) {
    $env:HOMECLOUD_SDK_ROOT = $SdkRoot
}
python -m pip install -q -e "${Root}[build]"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Dist "build")
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Dist $Artifact)

pyinstaller --noconfirm --clean --distpath $Dist --workpath (Join-Path $Dist "build") (Join-Path $Root "homecloud.spec")

Move-Item -Force (Join-Path $Dist "homecloud.exe") (Join-Path $Dist $Artifact)

$hash = Get-FileHash (Join-Path $Dist $Artifact) -Algorithm SHA256
"$($hash.Hash.ToLower())  $Artifact" | Set-Content (Join-Path $Dist "$Artifact.sha256")

Write-Host "Built: $(Join-Path $Dist $Artifact)"
