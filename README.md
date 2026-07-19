# homecloud-cli

Thin command-line wrapper over [`homecloud-sdk`](https://github.com/HomeCloudLab/homecloud-sdk),
distributed as a **single binary** (no Python required for end users).

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
homecloud login --browser   # passkeys / security keys
homecloud apps list
homecloud mq send orders --body '{"id": 1}'
homecloud so ls my-bucket
```

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for release pipeline and [docs/SMOKE_TEST.md](docs/SMOKE_TEST.md) for E2E verification.

## Developers — source install

This repo contains **only** `homecloud_cli` (Typer / Rich UI). Auth, HTTP, signing,
and SO/MQ live in the separate `homecloud-sdk` package.

```bash
# From a checkout that has both repos as siblings:
#   .../homecloud-sdk
#   .../homecloud-cli
pip install -e ../homecloud-sdk -e ".[dev]"
pytest tests/ -q
```

After PyPI publish:

```bash
pip install -e ".[dev]"   # pulls homecloud-sdk from PyPI
```

## Build standalone binary

PyInstaller bundles the installed `homecloud-sdk` + this CLI into one executable:

```bash
pip install -e ../homecloud-sdk -e ".[build]"
./scripts/build-binary.sh    # Linux/macOS
# or
.\scripts\build-binary.ps1  # Windows
```

## What CLI does NOT contain

HTTP, auth, signing, account resolution, or endpoint routing — all in `homecloud-sdk`.
