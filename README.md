# homecloud-cli

Command-line interface for the HomeCloud platform.

## Install

```bash
pip install -e .
```

## Quick start

1. Create an Access Key in the Console (IAM → Access Keys) and download the credentials JSON.
2. Configure the CLI:

```bash
homecloud configure
# or import the file from the Console:
homecloud configure import ~/.homecloud/credentials.json
```

3. List queues (requires console login or saved session token):

```bash
homecloud login
homecloud queues list
```

4. Send/receive messages on the MQ data plane (uses Access Key signing):

```bash
homecloud mq send my-queue --body '{"hello":"world"}'
homecloud mq receive my-queue
```

## Configuration

Credentials are stored at `~/.homecloud/credentials` (mode `0600`).

The file supports multiple profiles:

```json
{
  "version": 1,
  "default_profile": "default",
  "profiles": {
    "default": {
      "console_url": "https://console.holab.abrdns.com/api/v1",
      "mq_url": "https://mq.holab.abrdns.com",
      "default_account_id": "00000000-0000-0000-0000-000000000000",
      "access_key_id": "HCAK...",
      "secret_access_key": "..."
    }
  }
}
```

The flat format exported by the Console UI is also accepted.

## Global options

- `--profile NAME` — use a named profile (default: `default`)
- `--output table|json|yaml` — output format (default: `table`)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q
```
