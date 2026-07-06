# GitHub Secrets — CLI release upload to MinIO

Public bucket: https://homecloud-cli.so.holab.abrdns.com/releases/

## HomeCloud policy format (HOLAB / SO)

**Not AWS S3 syntax.** Use:

| Field | HomeCloud |
|-------|-----------|
| Actions | `so:GetObject`, `so:PutObject`, `so:ListBucket` |
| Resource ARN | `arn:holab:so:::homecloud-cli/*` |

Reference policies in `homecloud-infra/docs/policies/`:

- `homecloud-cli-public-read.json` — bucket public download
- `homecloud-cli-release-ci-user.json` — CI user (write only to this bucket)

---

## Do NOT use root MinIO credentials in GitHub

Create a dedicated user, e.g. `github-cli-release`:

1. MinIO Console → **Identity → Users → Create**
2. Attach policy from `homecloud-cli-release-ci-user.json`
3. Copy access key + secret **of that user only**

---

## GitHub Secrets (`homecloud-cli` repo)

Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|--------|
| `HOMECLOUD_S3_ENDPOINT` | `https://so.holab.abrdns.com` (S3 API — GET public; PUT/DELETE with SigV4) |
| `HOMECLOUD_CLI_S3_ACCESS_KEY` | access key of `github-cli-release` |
| `HOMECLOUD_CLI_S3_SECRET_KEY` | secret of `github-cli-release` |

---

## Public read (bucket policy — already open)

Example (Console / bucket policy):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": ["so:GetObject"],
      "Resource": ["arn:holab:so:::homecloud-cli/*"]
    }
  ]
}
```

---

## Bucket layout (auto on every tag)

```text
releases/
  latest/
    VERSION
    homecloud-linux-amd64
    ...
  v0.2.4/
    homecloud-linux-amd64
    ...
```

## Test download

```bash
curl -fsSL https://homecloud-cli.so.holab.abrdns.com/releases/latest/homecloud-linux-amd64 -o homecloud
chmod +x homecloud
./homecloud version
```
