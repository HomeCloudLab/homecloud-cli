# HomeCloud CLI — Binary Distribution

Public bucket: **https://homecloud-cli.so.holab.abrdns.com** (open read)

## Install

```bash
curl -fsSL https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-linux-amd64 -o homecloud
chmod +x homecloud
sudo mv homecloud /usr/local/bin/
homecloud version
```

Or use the installer script from this repo (`install/install.sh`).

Windows:

```powershell
$url = "https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-windows-amd64.exe"
Invoke-WebRequest $url -OutFile "$env:LOCALAPPDATA\Programs\homecloud\homecloud.exe"
```

## Direct download URLs

```text
https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-linux-amd64
https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-darwin-arm64
https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-windows-amd64.exe
```

Intel Mac (`darwin-amd64`) is temporarily omitted from CI — GitHub `macos-13` runners rarely become available on free tier.

Pinned version:

```text
https://homecloud-cli.so.holab.abrdns.com/releases/v0.2.4/homecloud-linux-amd64
```

## Bucket layout

```text
homecloud-cli/   (bucket — public read)
  releases/
    latest/          ← updated on every tag
      VERSION
      homecloud-linux-amd64
      homecloud-linux-amd64.sha256
      ...
    v0.2.4/          ← immutable per release
      VERSION
      homecloud-linux-amd64
      ...
```

## CI/CD (automatic)

Tag `v*` → GitHub Actions `release.yml`:

1. Build 3 platform binaries (linux, darwin-arm64, windows)
2. GitHub Release assets
3. Upload to MinIO → `releases/v<version>/` + `releases/latest/`

Required secrets: see [GITHUB_SECRETS.md](./GITHUB_SECRETS.md)

## GitHub Releases (mirror)

https://github.com/HomeCloudLab/homecloud-cli/releases

## Build locally

```bash
./scripts/build-binary.sh
# output: dist/homecloud-<os>-<arch>
```
