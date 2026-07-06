"""Typer CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from homecloud_cli import __version__
from homecloud_cli.client import ConsoleClient, HomeCloudError, MqClient
from homecloud_cli.config import (
    DEFAULT_CONSOLE_URL,
    DEFAULT_MQ_URL,
    DEFAULT_PROFILE,
    Profile,
    credentials_path,
    load_credentials,
    mask_secret,
    upsert_profile,
)
from homecloud_cli.output import emit

app = typer.Typer(
    no_args_is_help=True,
    help="HomeCloud command-line interface",
)
configure_app = typer.Typer(help="Manage credentials and profiles")
config_app = typer.Typer(help="Show current configuration")
accounts_app = typer.Typer(help="Account commands")
queues_app = typer.Typer(help="Queue commands (console API)")
mq_app = typer.Typer(help="MQ data plane commands (Access Key)")

app.add_typer(configure_app, name="configure")
app.add_typer(config_app, name="config")
app.add_typer(accounts_app, name="accounts")
app.add_typer(queues_app, name="queues")
app.add_typer(mq_app, name="mq")


def _profile_option(profile: Optional[str]) -> str:
    return profile or DEFAULT_PROFILE


def _output_option(output: str) -> str:
    normalized = output.lower()
    if normalized not in {"table", "json", "yaml"}:
        raise typer.BadParameter("output must be table, json, or yaml")
    return normalized


def _load_profile(profile_name: Optional[str]) -> Profile:
    credentials = load_credentials()
    return credentials.get_profile(_profile_option(profile_name))


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


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
) -> None:
    pass


@configure_app.callback(invoke_without_command=True)
def configure_wizard(
    ctx: typer.Context,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    profile_name = _profile_option(profile)
    typer.echo(f"Configuring profile: {profile_name}")

    console_url = typer.prompt("Console API URL", default=DEFAULT_CONSOLE_URL)
    mq_url = typer.prompt("MQ data plane URL", default=DEFAULT_MQ_URL)
    account_id = typer.prompt("Default account ID")
    access_key_id = typer.prompt("Access Key ID")
    secret_access_key = typer.prompt("Secret Access Key", hide_input=True)

    saved = upsert_profile(
        Profile(
            name=profile_name,
            console_url=console_url,
            mq_url=mq_url,
            default_account_id=account_id,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
    )
    typer.echo(f"Saved credentials to {saved}")


@configure_app.command("import")
def configure_import(
    file: Annotated[Path, typer.Argument(help="Credentials JSON from Console UI")],
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
) -> None:
    raw = json.loads(file.read_text(encoding="utf-8"))
    profile_name = _profile_option(profile)

    profile_data = Profile(
        name=profile_name,
        console_url=raw.get("console_url", DEFAULT_CONSOLE_URL),
        mq_url=raw.get("mq_url", DEFAULT_MQ_URL),
        default_account_id=raw.get("default_account_id"),
        access_key_id=raw.get("access_key_id"),
        secret_access_key=raw.get("secret_access_key"),
    )
    saved = upsert_profile(profile_data)
    typer.echo(f"Imported credentials into {saved} (profile: {profile_name})")


@config_app.command("show")
def config_show(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    credentials = load_credentials()
    active = credentials.get_profile(_profile_option(profile))
    data = {
        "credentials_file": str(credentials_path()),
        "default_profile": credentials.default_profile,
        "profile": active.name,
        "console_url": active.console_url,
        "mq_url": active.mq_url,
        "default_account_id": active.default_account_id,
        "access_key_id": active.access_key_id,
        "secret_access_key": mask_secret(active.secret_access_key),
        "logged_in": bool(active.access_token),
    }
    emit(data, output_format=_output_option(output))


@app.command("login")
def login(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    email: Annotated[Optional[str], typer.Option(help="Console email")] = None,
    password: Annotated[Optional[str], typer.Option(help="Console password", hide_input=True)] = None,
) -> None:
    profile_name = _profile_option(profile)
    active = _load_profile(profile_name)
    email_value = email or typer.prompt("Email")
    password_value = password or typer.prompt("Password", hide_input=True)

    client = ConsoleClient(active)
    try:
        token = client.login(email_value, password_value)
    except HomeCloudError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    active.access_token = token
    upsert_profile(active, make_default=profile_name == DEFAULT_PROFILE)
    typer.echo(f"Logged in (profile: {profile_name})")


@accounts_app.command("list")
def accounts_list(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    active = _load_profile(profile)
    client = ConsoleClient(active)
    try:
        items = client.list_accounts()
    except (HomeCloudError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    emit(
        items,
        output_format=_output_option(output),
        columns=["id", "name", "slug", "status"],
    )


@queues_app.command("list")
def queues_list(
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    account_id: Annotated[Optional[str], typer.Option(help="Account ID override")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "table",
) -> None:
    active = _load_profile(profile)
    account = account_id or active.default_account_id
    if not account:
        typer.secho("default_account_id is required", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    client = ConsoleClient(active)
    try:
        items = client.list_queues(account)
    except (HomeCloudError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    emit(
        items,
        output_format=_output_option(output),
        columns=["name", "status", "provider", "resource_type"],
    )


@mq_app.command("send")
def mq_send(
    queue_name: Annotated[str, typer.Argument(help="Queue name")],
    body: Annotated[str, typer.Option(help="JSON message body")] = "{}",
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    active = _load_profile(profile)
    client = MqClient(active)
    try:
        payload = json.loads(body)
        result = client.send_message(queue_name, body=payload)
    except (HomeCloudError, ValueError, json.JSONDecodeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    emit(result, output_format=_output_option(output))


@mq_app.command("receive")
def mq_receive(
    queue_name: Annotated[str, typer.Argument(help="Queue name")],
    max_messages: Annotated[int, typer.Option(help="Max messages (1-10)")] = 1,
    wait_seconds: Annotated[int, typer.Option(help="Long-poll wait (1-30s)")] = 20,
    profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
    output: Annotated[str, typer.Option(help="Output format")] = "json",
) -> None:
    active = _load_profile(profile)
    client = MqClient(active)
    try:
        items = client.receive_messages(
            queue_name,
            max_messages=max_messages,
            wait_seconds=wait_seconds,
        )
    except (HomeCloudError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    emit(items, output_format=_output_option(output))


def main() -> None:
    app()
