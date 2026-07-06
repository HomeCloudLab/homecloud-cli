"""Typer CLI — thin wrapper over homecloud_sdk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

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

app.add_typer(configure_app, name="configure")
app.add_typer(config_app, name="config")
app.add_typer(accounts_app, name="accounts")
app.add_typer(apps_app, name="apps")
app.add_typer(queues_app, name="queues")
app.add_typer(mq_app, name="mq")


def _profile_option(profile: Optional[str]) -> str | None:
    return profile


def _client(profile: Optional[str]) -> HomeCloudClient:
    return HomeCloudClient(profile=profile)


def _output_option(output: str) -> str:
    normalized = output.lower()
    if normalized not in {"table", "json", "yaml"}:
        raise typer.BadParameter("output must be table, json, or yaml")
    return normalized


def _handle_error(exc: Exception) -> None:
    typer.secho(str(exc), fg=typer.colors.RED, err=True)
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
    profile: Annotated[Optional[str], typer.Option(help="Configuration profile")] = None,
) -> None:
    if profile:
        import os

        os.environ["HOMECLOUD_PROFILE"] = profile


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
    email: Annotated[Optional[str], typer.Option(help="Email")] = None,
    password: Annotated[Optional[str], typer.Option(help="Password", hide_input=True)] = None,
) -> None:
    client = _client(profile)
    try:
        client.login(
            email or typer.prompt("Email"),
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
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    try:
        payload = json.loads(body)
        result = _client(profile).mq.send(queue_name, payload)
    except (HomeCloudError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
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
    except (HomeCloudError, FileNotFoundError, ValueError) as exc:
        _handle_error(exc)
    emit(items, output_format=_output_option(output))


def main() -> None:
    app()
