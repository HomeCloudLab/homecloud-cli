# GitHub Secrets — CLI release upload to MinIO

Add these in **homecloud-cli** → Settings → Secrets and variables → Actions:

| Secret | Example | Purpose |
|--------|---------|---------|
| `HOMECLOUD_S3_ENDPOINT` | `https://so.holab.abrdns.com` | MinIO S3 API (upload) |
| `HOMECLOUD_CLI_S3_ACCESS_KEY` | *(from platform .env)* | Write access |
| `HOMECLOUD_CLI_S3_SECRET_KEY` | *(from platform .env)* | Write access |

Public read (no auth): https://homecloud-cli.so.holab.abrdns.com/releases/

## Bucket layout (auto on every tag)

```text
releases/
  latest/
    VERSION
    homecloud-linux-amd64
    homecloud-linux-amd64.sha256
    ...
  v0.2.4/
    VERSION
    homecloud-linux-amd64
    ...
```

## Test download

```bash
curl -fsSL https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-linux-amd64 -o homecloud
chmod +x homecloud
./homecloud version
```
