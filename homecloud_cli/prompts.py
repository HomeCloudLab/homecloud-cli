"""Interactive arrow-key menus for the CLI (React/Vite-style selects)."""

from __future__ import annotations

import sys
from typing import Literal, TypeVar

import questionary
from questionary import Choice, Style

from homecloud_core.errors import HomeCloudError

T = TypeVar("T")

LoginMode = Literal["terminal", "browser"]
MfaChoice = Literal["totp", "browser"]

_STYLE = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:cyan"),
        ("instruction", "fg:ansibrightblack"),
        ("text", ""),
    ]
)


def is_interactive() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def select_one(
    message: str,
    choices: list[tuple[str, T]],
    *,
    default: T | None = None,
) -> T:
    """Arrow-key select. ``choices`` is (label, value) pairs."""
    if not choices:
        raise HomeCloudError("No choices available")
    if not is_interactive():
        if default is not None:
            for _, value in choices:
                if value == default:
                    return value
        return choices[0][1]

    q_choices = [Choice(title=label, value=value) for label, value in choices]
    default_choice = None
    if default is not None:
        for choice in q_choices:
            if choice.value == default:
                default_choice = choice
                break

    result = questionary.select(
        message,
        choices=q_choices,
        default=default_choice,
        style=_STYLE,
        instruction="(↑/↓ to move, Enter to confirm)",
    ).ask()
    if result is None:
        raise HomeCloudError("Cancelled")
    return result  # type: ignore[return-value]


def select_login_mode(*, default: LoginMode = "terminal") -> LoginMode:
    return select_one(
        "How do you want to sign in?",
        [
            (
                "Terminal  — username, password, authenticator / backup code",
                "terminal",
            ),
            (
                "Browser   — passkeys & security keys (recommended if you use a passkey)",
                "browser",
            ),
        ],
        default=default,
    )


def select_mfa_method(methods: list[str], *, passkeys: list[dict] | None = None) -> MfaChoice:
    """
    Choose second factor when MFA_REQUIRED lists available methods.

    Passkey finishes in the browser (CLI cannot drive WebAuthn).
    """
    normalized = {str(m).lower() for m in methods}
    has_totp = "totp" in normalized or not normalized
    has_passkey = "passkey" in normalized

    choices: list[tuple[str, MfaChoice]] = []
    if has_totp:
        choices.append(
            ("Authenticator app or backup code", "totp"),
        )
    if has_passkey:
        nicknames = [
            str(p.get("nickname") or "Passkey")
            for p in (passkeys or [])
            if isinstance(p, dict)
        ]
        suffix = f" ({', '.join(nicknames)})" if nicknames else ""
        choices.append(
            (f"Passkey / security key{suffix} — opens browser", "browser"),
        )

    if not choices:
        choices.append(("Authenticator app or backup code", "totp"))

    if len(choices) == 1:
        return choices[0][1]

    return select_one(
        "Choose second factor",
        choices,
        default="totp" if has_totp else "browser",
    )
