"""Typer CLI — thin wrapper over homecloud_sdk."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from homecloud_core.defaults import DEFAULT_PROFILE
from homecloud_core.errors import HomeCloudError
from homecloud_sdk import HomeCloudClient

from homecloud_cli import __version__
from homecloud_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="HomeCloud command-line interface")
configure_app = typer.Typer(help="Set up Access Keys and profiles")
config_app = typer.Typer(help="Show current configuration")
accounts_app = typer.Typer(help="Account commands")
apps_app = typer.Typer(help="Application commands")
queues_app = typer.Typer(help="Queue commands")
mq_app = typer.Typer(help="Message queue commands")

so_app = typer.Typer(help="Object storage commands")

app.add_typer(configure_app, name="configure")
app.add_typer(config_app, name="config")
app.add_typer(accounts_app, name="accounts")
app.add_typer(apps_app, name="apps")
app.add_typer(queues_app, name="queues")
app.add_typer(mq_app, name="mq")
app.add_typer(so_app, name="so")


def _profile_option(profile: Optional[str]) -> str | None:
    return profile


def _client(profile: Optional[str]) -> HomeCloudClient:
    return HomeCloudClient(profile=profile)


def _output_option(output: str) -> str:
    normalized = output.lower()
    if normalized not in {"table", "json", "yaml"}:
        raise typer.BadParameter("output must be table, json, or yaml")
    return normalized


def _repair_powershell_json(raw: str) -> str:
    """Quote bare keys/values when PowerShell strips JSON double quotes from argv."""
    inner = raw.strip()
    if not (inner.startswith("{") and inner.endswith("}")):
        return inner
    inner = re.sub(r"([{,]\s*)([A-Za-z_][\w-]*)(\s*:)", r'\1"\2"\3', inner)
    inner = re.sub(r'(:\s*)([A-Za-z_][\w-]*)(\s*[,}])', r'\1"\2"\3', inner)
    return inner


def _parse_mq_body(raw: str) -> dict[str, Any]:
    last_exc: json.JSONDecodeError | None = None
    for candidate in (raw, _repair_powershell_json(raw)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if not isinstance(parsed, dict):
            raise typer.BadParameter("--body must be a JSON object")
        return parsed
    assert last_exc is not None
    raise last_exc


def _load_mq_body(body: str, body_file: Path | None) -> dict[str, Any]:
    if body_file is not None:
        return _parse_mq_body(body_file.read_text(encoding="utf-8"))
    return _parse_mq_body(body)


def _format_error(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return (
            f"Invalid JSON in --body: {exc.msg}\n"
            'PowerShell: --body "{`"hello`":`"world`"}"  '
            'or --body ''{"hello":"world"}'''
        )
    if isinstance(exc, HomeCloudError):
        if exc.status_code == 404 and isinstance(exc.detail, str):
            return exc.detail
        if exc.detail is not None and exc.detail != str(exc):
            if isinstance(exc.detail, str):
                return exc.detail
            return f"{exc} — {exc.detail}"
    return str(exc)


def _handle_error(exc: Exception) -> None:
    typer.secho(_format_error(exc), fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from exc


def version_callback(value: bool) -> None:
    if value:
        typer.echo(_version_line())
        raise typer.Exit()


def _version_line() -> str:
    import platform
    import sys

    runtime = "standalone" if getattr(sys, "frozen", False) else "source"
    return f"homecloud {__version__} ({platform.system().lower()}-{platform.machine()}, {runtime})"


@app.command("version")
def version_cmd() -> None:
    """Show CLI version and build metadata."""
    typer.echo(_version_line())


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Credentials profile name"),
    ] = None,
    access_key_id: Annotated[
        Optional[str],
        typer.Option(
            "--access-key-id",
            envvar="HOMECLOUD_ACCESS_KEY_ID",
            help="Access Key ID (overrides saved profile)",
        ),
    ] = None,
    secret_access_key: Annotated[
        Optional[str],
        typer.Option(
            "--secret-access-key",
            envvar="HOMECLOUD_SECRET_ACCESS_KEY",
            help="Secret Access Key (overrides saved profile)",
        ),
    ] = None,
    apex: Annotated[
        Optional[str],
        typer.Option(
            "--apex",
            envvar="HOMECLOUD_APEX",
            help="Platform apex domain (e.g. holab.abrdns.com)",
        ),
    ] = None,
) -> None:
    import os

    if profile:
        os.environ["HOMECLOUD_PROFILE"] = profile
    if access_key_id is not None:
        os.environ["HOMECLOUD_ACCESS_KEY_ID"] = access_key_id
    if secret_access_key is not None:
        os.environ["HOMECLOUD_SECRET_ACCESS_KEY"] = secret_access_key
    if apex is not None:
        os.environ["HOMECLOUD_APEX"] = apex


@configure_app.callback(invoke_without_command=True)
def configure_wizard(
    ctx: typer.Context,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    profile_name = profile or DEFAULT_PROFILE
    typer.echo(f"Configuring profile: {profile_name}")

    access_key_id = typer.prompt("Access Key ID")
    secret_access_key = typer.prompt("Secret Access Key", hide_input=True)

    client = HomeCloudClient(profile=profile_name)
    client.configure(
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )
    typer.echo("Configuration saved.")


@configure_app.command("import")
def configure_import(
    file: Annotated[Path, typer.Argument(help="Credentials JSON from Console")],
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    raw = json.loads(file.read_text(encoding="utf-8"))
    client = HomeCloudClient(profile=profile or DEFAULT_PROFILE)
    client.import_credentials(raw)
    typer.echo("Credentials imported.")


@config_app.command("show")
def config_show(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    try:
        summary = _client(profile).config_summary()
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(summary, output_format=_output_option(output))


@app.command("login")
def login(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    username: Annotated[Optional[str], typer.Option(help="Console username")] = None,
    password: Annotated[Optional[str], typer.Option(help="Password", hide_input=True)] = None,
) -> None:
    client = _client(profile)
    try:
        client.login(
            username or typer.prompt("Username"),
            password or typer.prompt("Password", hide_input=True),
        )
    except HomeCloudError as exc:
        _handle_error(exc)
    typer.echo("Logged in.")


@accounts_app.command("list")
def accounts_list(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    try:
        items = _client(profile).accounts.list()
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["name", "slug", "status"])


@accounts_app.command("switch")
def accounts_switch(
    account_ref: Annotated[str, typer.Argument(help="Account name or slug")],
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    try:
        _client(profile).accounts.switch(account_ref)
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    typer.echo(f"Switched to account: {account_ref}")


@apps_app.command("list")
def apps_list(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    try:
        items = _client(profile).apps.list()
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["name", "slug", "status"])


@queues_app.command("list")
def queues_list(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    try:
        items = _client(profile).queues.list()
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["name", "status"])


@mq_app.command("send")
def mq_send(
    queue_name: Annotated[str, typer.Argument(help="Queue name")],
    body: Annotated[str, typer.Option(help="JSON message body")] = "{}",
    body_file: Annotated[
        Optional[Path],
        typer.Option("--body-file", help="Read JSON message body from a file", exists=True, readable=True),
    ] = None,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    try:
        payload = _load_mq_body(body, body_file)
        result = _client(profile).mq.send(queue_name, payload)
    except json.JSONDecodeError as exc:
        _handle_error(exc)
    except HomeCloudError as exc:
        if exc.status_code == 404 and exc.detail == "Queue not found":
            _handle_error(
                HomeCloudError(
                    f"Queue '{queue_name}' not found. "
                    "Create it in the console (Queues) or check the name with: homecloud queues list"
                )
            )
        _handle_error(exc)
    except (FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(result, output_format=_output_option(output))


@mq_app.command("receive")
def mq_receive(
    queue_name: Annotated[str, typer.Argument(help="Queue name")],
    max_messages: Annotated[int, typer.Option(help="Max messages (1-10)")] = 1,
    wait_seconds: Annotated[int, typer.Option(help="Long-poll wait (1-30s)")] = 20,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    try:
        items = _client(profile).mq.receive(
            queue_name,
            max_messages=max_messages,
            wait_seconds=wait_seconds,
        )
    except HomeCloudError as exc:
        if exc.status_code == 404 and exc.detail == "Queue not found":
            _handle_error(
                HomeCloudError(
                    f"Queue '{queue_name}' not found. "
                    "Create it in the console (Queues) or check the name with: homecloud queues list"
                )
            )
        _handle_error(exc)
    except (FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output))


def _parse_so_uri(target: str) -> tuple[str, str]:
    """Return (bucket, key_prefix) from so://bucket/path or bucket/path."""
    cleaned = target.removeprefix("so://").removeprefix("s3://").strip("/")
    if not cleaned:
        raise typer.BadParameter("URI must include a bucket name")
    parts = cleaned.split("/", 1)
    bucket_name = parts[0]
    key_prefix = parts[1] if len(parts) > 1 else ""
    return bucket_name, key_prefix


def _format_so_uri(bucket: str, key: str = "") -> str:
    if key:
        return f"so://{bucket}/{key.lstrip('/')}"
    return f"so://{bucket}/"


@so_app.command("sync")
def so_sync(
    local_path: Annotated[Path, typer.Argument(help="Local directory to upload")],
    destination: Annotated[str, typer.Argument(help="so://bucket/ or so://bucket/prefix/")],
    delete: Annotated[
        bool,
        typer.Option("--delete", help="Remove remote objects not present locally"),
    ] = False,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    """Sync local directory to bucket (upload only; use --delete to mirror)."""
    bucket_name, prefix = _parse_so_uri(destination)
    if not local_path.is_dir():
        raise typer.BadParameter(f"Not a directory: {local_path}")
    try:
        result = _client(profile).storage.sync_local_to_bucket(
            local_path,
            bucket_name,
            prefix=prefix,
            delete=delete,
        )
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(result, output_format=_output_option(output))


@so_app.command("ls-buckets")
def so_ls_buckets(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    """List storage buckets (console API — requires login)."""
    try:
        items = _client(profile).storage.list_buckets()
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["name", "status"])


@so_app.command("ls")
def so_ls(
    bucket: Annotated[str, typer.Argument(help="Bucket name")],
    prefix: Annotated[str, typer.Option(help="Object key prefix")] = "",
    recursive: Annotated[bool, typer.Option(help="List recursively")] = False,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    """List objects in a bucket (data plane — Access Key)."""
    try:
        data = _client(profile).storage.list_objects(bucket, prefix=prefix, recursive=recursive)
        items = data.get("items", [])
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["key", "size", "last_modified"])


@so_app.command("cp")
def so_cp(
    local_path: Annotated[Path, typer.Argument(help="Local file path")],
    destination: Annotated[str, typer.Argument(help="so://bucket/key or bucket/key")],
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    """Upload a file to a bucket (data plane — Access Key)."""
    bucket_name, object_key = _parse_so_uri(destination)
    if not object_key:
        raise typer.BadParameter("destination must be so://bucket/key or bucket/key")
    try:
        result = _client(profile).storage.upload(bucket_name, local_path.as_posix(), key=object_key)
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(result, output_format=_output_option(output))


@so_app.command("rm")
def so_rm(
    uri: Annotated[str, typer.Argument(help="so://bucket/key, so://bucket/, or bucket/prefix/")],
    recursive: Annotated[
        bool,
        typer.Option("--recursive", "-r", help="Delete all objects under bucket or prefix"),
    ] = False,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    """Delete an object, or recursively delete a bucket/prefix."""
    bucket_name, object_key = _parse_so_uri(uri)
    try:
        if recursive:
            count = _client(profile).storage.delete_recursive(bucket_name, prefix=object_key)
            scope = object_key or bucket_name
            typer.echo(f"Deleted {count} object(s) under {_format_so_uri(bucket_name, scope)}")
            return
        if not object_key:
            raise typer.BadParameter("Object key required unless --recursive is set")
        _client(profile).storage.delete(bucket_name, object_key)
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    typer.echo(f"Deleted {_format_so_uri(bucket_name, object_key)}")


def main() -> None:
    app()
