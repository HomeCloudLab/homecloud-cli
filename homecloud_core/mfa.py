"""Central MFA challenge handling for console API calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homecloud_core.errors import HomeCloudError

PromptFn = Callable[[str], str]


def is_mfa_required(exc: HomeCloudError) -> bool:
    return exc.status_code == 403 and exc.error_code == "MFA_REQUIRED"


def prompt_verification_code(prompt: PromptFn | None = None) -> str:
    """Prompt for TOTP or backup code. Never cache the result."""
    ask = prompt or (lambda msg: input(f"{msg}: ").strip())
    code = ask("Verification code")
    if not code:
        raise HomeCloudError("Verification code is required")
    return code.strip()


class MfaResolver:
    """
    Completes MFA_REQUIRED challenges for console requests.

    - Login challenge (`mfa_token` in details): POST auth/login with mfa_token + mfa_code
    - Step-up (no mfa_token): retry original JSON body with mfa_code injected

    Passkeys are not completed in-terminal — use `homecloud login --browser`.
    """

    def __init__(
        self,
        *,
        mfa_code: str | None = None,
        prompt: PromptFn | None = None,
        interactive: bool = True,
    ) -> None:
        self._mfa_code = mfa_code
        self._prompt = prompt
        self._interactive = interactive

    def obtain_code(self, *, methods: list[str] | None = None) -> str:
        if self._mfa_code:
            code = self._mfa_code
            self._mfa_code = None  # one-shot — never reuse across challenges
            return code
        if not self._interactive:
            raise HomeCloudError(
                "MFA required. Re-run with --mfa-code, or use: homecloud login --browser"
            )
        methods = methods or []
        if methods and "totp" not in methods and "passkey" in methods:
            raise HomeCloudError(
                "This account requires a passkey. Use: homecloud login --browser"
            )
        return prompt_verification_code(self._prompt)

    def resolve(
        self,
        exc: HomeCloudError,
        *,
        method: str,
        path: str,
        json_body: Any | None,
        retry: Callable[..., Any],
    ) -> Any:
        details = exc.error_details
        mfa_token = details.get("mfa_token")
        methods = details.get("methods") if isinstance(details.get("methods"), list) else None
        code = self.obtain_code(methods=[str(m) for m in methods] if methods else None)

        if mfa_token:
            return retry(
                "POST",
                "auth/login",
                json={"mfa_token": mfa_token, "mfa_code": code},
                require_auth=False,
                _skip_mfa=True,
            )

        body = dict(json_body) if isinstance(json_body, dict) else {}
        body["mfa_code"] = code
        return retry(method, path, json=body, _skip_mfa=True)
