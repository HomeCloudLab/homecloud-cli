# HomeCloud CLI — Binary Distribution

AWS-style single-binary distribution. End users do **not** need Python or pip.

## Install (recommended)

```bash
curl -sSL https://install.homecloud.dev | bash
```

Windows (PowerShell):

```powershell
irm https://install.homecloud.dev/windows | iex
```

## Direct download

```text
https://cli.homecloud.dev/releases/latest/homecloud-linux-amd64
https://cli.homecloud.dev/releases/latest/homecloud-darwin-arm64
https://cli.homecloud.dev/releases/latest/homecloud-darwin-amd64
https://cli.homecloud.dev/releases/latest/homecloud-windows-amd64.exe
```

## Storage layout (S3-compatible)

```text
homecloud-cli/
  releases/
    v0.2.0/
      homecloud-linux-amd64
      homecloud-linux-amd64.sha256
      homecloud-darwin-arm64
      ...
    latest/
      homecloud-linux-amd64    # pointer copy (same object or redirect)
```

Homelab MinIO bucket: configure `HOMECLOUD_CLI_BUCKET` and DNS:

| Host | Purpose |
|------|---------|
| `cli.homecloud.dev` | Binary downloads (`/releases/...`) |
| `install.homecloud.dev` | Serves `install.sh` / `install.ps1` |

## Build locally

```bash
# Unix
./scripts/build-binary.sh

# Windows
.\scripts\build-binary.ps1
```

Output: `dist/homecloud-<os>-<arch>`

## Release pipeline

Tag `v*` → GitHub Actions `release.yml`:

1. Matrix build (linux-amd64, darwin-amd64, darwin-arm64, windows-amd64)
2. Strip debug symbols
3. SHA256 checksums
4. GitHub Release assets
5. Optional S3 upload (secrets: `HOMECLOUD_S3_ENDPOINT`, `HOMECLOUD_CLI_S3_*`)

## Architecture

```text
homecloud (binary)
  └── homecloud-cli/     thin Typer wrapper
        └── homecloud-sdk/
              └── homecloud_core/   auth, sessions, signing, routing
```

User experience:

```bash
homecloud configure
homecloud login
homecloud apps list
homecloud mq send orders --body '{"id":1}'
homecloud version
```

No JWT, HMAC, account IDs, or endpoint URLs exposed to users.

## Future

- `homecloud update` — self-update from `releases/latest`
- Code signing (macOS notarization, Windows Authenticode)
