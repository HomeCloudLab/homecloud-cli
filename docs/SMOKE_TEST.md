# CLI E2E Smoke Test

## Prerequisites

1. Access Key with `*` or MQ + SO permissions
2. A queue (default: `test123`)
3. A bucket (default: `media`)

## Configure

```bash
homecloud configure
# or
export HOMECLOUD_ACCESS_KEY_ID=HCAK...
export HOMECLOUD_SECRET_ACCESS_KEY=...
export HOMECLOUD_ACCOUNT_ID=<account-uuid>
```

## Run (source install)

```bash
cd homecloud-cli
pip install -e .
export HOMECLOUD_QUEUE=test123
export HOMECLOUD_SO_BUCKET=media
python scripts/smoke-e2e.py
```

## Run (standalone binary)

After `homecloud configure`:

```bash
homecloud mq send test123 --body '{"smoke": true}'
homecloud mq receive test123 --wait-seconds 5
# Fast path: receive and ack in one call
# homecloud mq receive test123 --max-messages 10 --delete
homecloud so ls media
homecloud so cp ./file.txt s3://media/path/file.txt
homecloud so rm s3://media/path/file.txt
```

`homecloud so ls-buckets` requires `homecloud login` (console JWT).

Expected output from script: `SMOKE_OK`
