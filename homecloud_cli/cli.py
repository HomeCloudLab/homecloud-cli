"""Typer CLI — thin wrapper over homecloud_sdk."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

import typer
from homecloud_core.defaults import DEFAULT_PROFILE
from homecloud_core.errors import HomeCloudError
from homecloud_sdk import HomeCloudClient
from homecloud_sdk.so_parallel import DEFAULT_SO_WORKERS
from rich.console import Console

from homecloud_cli import __version__
from homecloud_cli.output import emit
from homecloud_cli.so_progress import SoTransferProgress
from homecloud_cli.transfer_progress import TransferProgress

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


def _client(
    profile: Optional[str],
    *,
    mfa_code: Optional[str] = None,
    interactive_mfa: bool = True,
) -> HomeCloudClient:
    return HomeCloudClient(
        profile=profile,
        mfa_code=mfa_code,
        interactive_mfa=interactive_mfa,
        mfa_prompt=lambda msg: typer.prompt(msg),
    )


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


def _mq_body_error_message(exc: json.JSONDecodeError) -> str:
    return (
        f"Invalid JSON in --body: {exc.msg}\n"
        'PowerShell: --body "{`"hello`":`"world`"}"  '
        'or --body ''{"hello":"world"}'''
    )


def _format_error(exc: Exception) -> str:
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
    mfa_code: Annotated[
        Optional[str],
        typer.Option("--mfa-code", help="TOTP or backup code (non-interactive MFA)"),
    ] = None,
    browser: Annotated[
        bool,
        typer.Option("--browser", help="Open Console in a browser (passkeys / security keys)"),
    ] = False,
) -> None:
    """Sign in to the Console API (JWT). Supports MFA and browser/passkey login."""
    client = _client(profile, mfa_code=mfa_code)
    try:
        if browser:
            typer.echo("Opening browser...")

            def _on_waiting(uri: str) -> None:
                typer.echo("Complete authentication in your browser.")
                typer.echo(f"  {uri}")
                typer.echo("Waiting for authentication...")

            client.login_browser(open_browser=True, on_waiting=_on_waiting)
        else:
            client.login(
                username or typer.prompt("Username"),
                password or typer.prompt("Password", hide_input=True),
                mfa_code=mfa_code,
            )
    except HomeCloudError as exc:
        _handle_error(exc)
    typer.echo("✓ Logged in")


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
        _handle_error(HomeCloudError(_mq_body_error_message(exc)))
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


def _is_so_uri(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith("so://") or lowered.startswith("s3://")


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


def _show_transfer_progress(output: str) -> bool:
    return _output_option(output) != "json"


def _run_so_sync_transfer(
    *,
    label: str,
    action: Literal["upload", "download"],
    show_progress: bool,
    sync_call: Callable[..., dict[str, int]],
) -> dict[str, Any]:
    progress: TransferProgress | None = None

    def on_transfer_begin(total_bytes: int, files_total: int) -> None:
        nonlocal progress
        if not show_progress:
            return
        progress = TransferProgress(label, action, total_bytes, files_total)
        progress.__enter__()

    def on_bytes(nbytes: int) -> None:
        if progress is not None:
            progress.add_bytes(nbytes)

    def on_file_begin(key: str) -> None:
        if progress is not None:
            progress.file_begin(key)

    def on_file_complete(key: str) -> None:
        if progress is not None:
            progress.file_complete(key)

    def on_skip(key: str) -> None:
        if progress is not None:
            progress.skip(key)

    def on_delete(key: str) -> None:
        if progress is not None:
            progress.delete(key)

    def on_status(msg: str) -> None:
        if not show_progress:
            return
        if progress is not None:
            progress.message(msg)
        else:
            Console(stderr=True).print(f"[cyan]{msg}[/]")

    file_done = on_file_complete
    kwargs: dict[str, Any] = {
        "on_transfer_begin": on_transfer_begin,
        "on_bytes": on_bytes,
        "on_file_begin": on_file_begin,
        "on_skip": on_skip,
        "on_delete": on_delete,
        "on_status": on_status,
    }
    if action == "upload":
        kwargs["on_upload"] = file_done
    else:
        kwargs["on_download"] = file_done

    try:
        return sync_call(**kwargs)
    finally:
        if progress is not None:
            progress.__exit__(None, None, None)


def _run_so_sync_upload(
    client: HomeCloudClient,
    local_path: Path,
    bucket_name: str,
    prefix: str,
    *,
    delete: bool,
    skip: bool,
    output: str,
    workers: int,
) -> dict[str, Any]:
    show_progress = _show_transfer_progress(output)
    dest = _format_so_uri(bucket_name, prefix)

    def sync_call(**kwargs: Any) -> dict[str, int]:
        return client.so.sync_local_to_bucket(
            local_path,
            bucket_name,
            prefix=prefix,
            delete=delete,
            skip=skip,
            max_workers=workers,
            **kwargs,
        )

    return _run_so_sync_transfer(
        label=f"sync → {dest}",
        action="upload",
        show_progress=show_progress,
        sync_call=sync_call,
    )


def _run_so_sync_download(
    client: HomeCloudClient,
    bucket_name: str,
    prefix: str,
    local_path: Path,
    *,
    delete: bool,
    skip: bool,
    output: str,
    workers: int,
) -> dict[str, Any]:
    show_progress = _show_transfer_progress(output)
    source = _format_so_uri(bucket_name, prefix)

    def sync_call(**kwargs: Any) -> dict[str, int]:
        return client.so.sync_bucket_to_local(
            bucket_name,
            local_path,
            prefix=prefix,
            delete=delete,
            skip=skip,
            max_workers=workers,
            **kwargs,
        )

    return _run_so_sync_transfer(
        label=f"sync ← {source}",
        action="download",
        show_progress=show_progress,
        sync_call=sync_call,
    )


@so_app.command("sync")
def so_sync(
    source: Annotated[str, typer.Argument(help="Local dir (upload) or so://bucket/ (download)")],
    destination: Annotated[str, typer.Argument(help="so://bucket/ (upload) or local dir (download)")],
    delete: Annotated[
        bool,
        typer.Option(
            "--delete",
            help="Mirror mode: remove extra files on the destination side",
        ),
    ] = False,
    skip: Annotated[
        bool,
        typer.Option(
            "--skip",
            help="Skip files whose size already matches on the destination (default: overwrite)",
        ),
    ] = False,
    workers: Annotated[
        int,
        typer.Option(
            "--workers",
            "-j",
            min=1,
            max=64,
            help=f"Parallel file transfers (default {DEFAULT_SO_WORKERS})",
        ),
    ] = DEFAULT_SO_WORKERS,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format (json suppresses live progress)")] = "table",
) -> None:
    """Sync local ↔ bucket. Overwrites by default. Upload: ./dir so://b/  Download: so://b/ ./dir"""
    source_is_so = _is_so_uri(source)
    dest_is_so = _is_so_uri(destination)

    if source_is_so and dest_is_so:
        raise typer.BadParameter(
            "Cannot sync remote to remote. Use: homecloud so sync ./local so://bucket/ "
            "or: homecloud so sync so://bucket/ ./local"
        )
    if not source_is_so and not dest_is_so:
        raise typer.BadParameter(
            "One argument must be a so:// URI. Upload: homecloud so sync ./local so://bucket/ "
            "Download: homecloud so sync so://bucket/ ./local"
        )

    client = _client(profile)
    try:
        if source_is_so:
            bucket_name, prefix = _parse_so_uri(source)
            local_path = Path(destination)
            result = _run_so_sync_download(
                client,
                bucket_name,
                prefix,
                local_path,
                delete=delete,
                skip=skip,
                output=output,
                workers=workers,
            )
        else:
            local_path = Path(source)
            if not local_path.is_dir():
                raise typer.BadParameter(f"Not a directory: {local_path}")
            bucket_name, prefix = _parse_so_uri(destination)
            result = _run_so_sync_upload(
                client,
                local_path,
                bucket_name,
                prefix,
                delete=delete,
                skip=skip,
                output=output,
                workers=workers,
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
        items = _client(profile).so.list_buckets()
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
        data = _client(profile).so.list_objects(bucket, prefix=prefix, recursive=recursive)
        items = data.get("items", [])
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output), columns=["key", "size", "last_modified"])


@so_app.command("cp")
def so_cp(
    source: Annotated[str, typer.Argument(help="Local file or so://bucket/key")],
    destination: Annotated[str, typer.Argument(help="so://bucket/key or local file path")],
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format (json suppresses live progress)")] = "table",
) -> None:
    """Copy a file local ↔ bucket. Upload: ./file so://b/k  Download: so://b/k ./file"""
    source_is_so = _is_so_uri(source)
    dest_is_so = _is_so_uri(destination)

    if source_is_so and dest_is_so:
        raise typer.BadParameter(
            "Cannot copy remote to remote. Use: homecloud so cp ./local so://bucket/key "
            "or: homecloud so cp so://bucket/key ./local"
        )
    if not source_is_so and not dest_is_so:
        raise typer.BadParameter(
            "One argument must be a so:// URI. Upload: homecloud so cp ./local so://bucket/key "
            "Download: homecloud so cp so://bucket/key ./local"
        )

    client = _client(profile)
    show_progress = _show_transfer_progress(output)

    try:
        if source_is_so:
            bucket_name, object_key = _parse_so_uri(source)
            if not object_key:
                raise typer.BadParameter("source must be so://bucket/key or bucket/key")
            uri = _format_so_uri(bucket_name, object_key)
            dest = Path(destination)
            if dest.exists() and dest.is_dir():
                dest = dest / object_key.rsplit("/", 1)[-1]
            dest.parent.mkdir(parents=True, exist_ok=True)

            file_size = 0
            try:
                meta = client.so.object_metadata(bucket_name, object_key)
                file_size = int(meta.get("size") or 0)
            except HomeCloudError:
                pass

            if show_progress:
                with TransferProgress(f"cp ← {uri}", "download", file_size, 1) as prog:
                    prog.file_begin(object_key)
                    result = client.so.download(
                        bucket_name,
                        object_key,
                        dest_path=dest,
                        on_bytes=prog.add_bytes,
                    )
                    prog.file_complete(object_key)
            else:
                result = client.so.download(bucket_name, object_key, dest_path=dest)
        else:
            local_path = Path(source)
            if not local_path.is_file():
                raise typer.BadParameter(f"Not a file: {local_path}")
            bucket_name, object_key = _parse_so_uri(destination)
            if not object_key:
                raise typer.BadParameter("destination must be so://bucket/key or bucket/key")
            uri = _format_so_uri(bucket_name, object_key)

            if show_progress:
                file_size = local_path.stat().st_size
                with TransferProgress(f"cp → {uri}", "upload", file_size, 1) as prog:
                    prog.file_begin(object_key)
                    result = client.so.upload(
                        bucket_name,
                        local_path.as_posix(),
                        key=object_key,
                        on_bytes=prog.add_bytes,
                    )
                    prog.file_complete(object_key)
            else:
                result = client.so.upload(
                    bucket_name, local_path.as_posix(), key=object_key
                )
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
    workers: Annotated[
        int,
        typer.Option(
            "--workers",
            "-j",
            min=1,
            max=64,
            help=f"Parallel deletes when using --recursive (default {DEFAULT_SO_WORKERS})",
        ),
    ] = DEFAULT_SO_WORKERS,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    """Delete an object, or recursively delete a bucket/prefix."""
    bucket_name, object_key = _parse_so_uri(uri)
    try:
        if recursive:
            scope = _format_so_uri(bucket_name, object_key or "")
            progress: SoTransferProgress | None = None

            def on_begin(total: int) -> None:
                nonlocal progress
                progress = SoTransferProgress(f"delete → {scope}", total)
                progress.__enter__()

            try:
                count = _client(profile).so.delete_recursive(
                    bucket_name,
                    prefix=object_key,
                    max_workers=workers,
                    on_begin=on_begin,
                    on_delete=progress.delete if progress else None,
                )
            finally:
                if progress is not None:
                    progress.__exit__(None, None, None)
            typer.echo(f"Deleted {count} object(s) under {scope}")
            return
        if not object_key:
            raise typer.BadParameter("Object key required unless --recursive is set")
        target = _format_so_uri(bucket_name, object_key)
        with SoTransferProgress(f"delete → {target}", 1) as prog:
            _client(profile).so.delete(bucket_name, object_key)
            prog.delete(target)
        return
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)


def main() -> None:
    app()
