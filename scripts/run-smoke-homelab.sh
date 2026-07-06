#!/usr/bin/env bash
# Run CLI E2E smoke on homelab (reads Access Key from Redis — do not log secrets).
set -euo pipefail
cd /tmp/homecloud-cli-smoke

ACCOUNT_ID=$(docker exec homecloud-platform-api-1 python -c '
import asyncio
from sqlalchemy import select
from app.db.session import async_session
from app.models import Account
async def main():
    async with async_session() as db:
        a = (await db.execute(select(Account).limit(1))).scalar_one()
        print(a.id)
asyncio.run(main())
')

KEY_ID=$(docker exec homecloud-platform-redis-1 redis-cli KEYS 'access_key:*' | head -1 | sed 's/access_key://')
SECRET=$(docker exec homecloud-platform-redis-1 redis-cli GET "access_key:${KEY_ID}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["secret"])')

pip install -q -e . 2>/dev/null || pip install -q -e .

export HOMECLOUD_ACCESS_KEY_ID="$KEY_ID"
export HOMECLOUD_SECRET_ACCESS_KEY="$SECRET"
export HOMECLOUD_ACCOUNT_ID="$ACCOUNT_ID"
export HOMECLOUD_QUEUE="${HOMECLOUD_QUEUE:-test123}"
export HOMECLOUD_SO_BUCKET="${HOMECLOUD_SO_BUCKET:-media}"

python3 scripts/smoke-e2e.py
