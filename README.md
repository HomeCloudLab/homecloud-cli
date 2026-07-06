# homecloud-cli

Thin command-line wrapper over `homecloud-sdk`, distributed as a **single binary** (no Python required for end users).

## End users — install

**Linux / macOS:**

```bash
curl -fsSL https://homecloud-cli.so.holab.abrdns.com/install/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://homecloud-cli.so.holab.abrdns.com/install/install.ps1 | iex
```

Direct binary URLs: [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)

```bash
homecloud version
homecloud configure
homecloud login
homecloud apps list
homecloud mq send orders --body '{"id": 1}'
homecloud so ls my-bucket
```

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for release pipeline and [docs/SMOKE_TEST.md](docs/SMOKE_TEST.md) for E2E verification.

## Developers — source install

SDK core (`homecloud_core`, `homecloud_sdk`) is **vendored in this repo** for standalone binary builds (no cross-repo checkout in CI).

Sync from `homecloud-sdk` when updating core logic, then commit here.

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

## Build standalone binary

```bash
pip install -e ../homecloud-sdk -e ".[build]"
./scripts/build-binary.sh    # Linux/macOS
# or
.\scripts\build-binary.ps1  # Windows
```

## What CLI does NOT contain

HTTP, auth, signing, account resolution, or endpoint routing — all in `homecloud-sdk` → `homecloud_core`.
