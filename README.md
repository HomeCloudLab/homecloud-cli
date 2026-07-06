# homecloud-cli

Thin command-line wrapper over `homecloud-sdk`, distributed as a **single binary** (no Python required for end users).

## End users — install

```bash
curl -sSL https://install.homecloud.dev | bash
```

```bash
homecloud version
homecloud configure
homecloud login
homecloud apps list
homecloud mq send orders --body '{"id": 1}'
```

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for release pipeline and storage layout.

## Developers — source install

```bash
pip install -e ../homecloud-sdk
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
