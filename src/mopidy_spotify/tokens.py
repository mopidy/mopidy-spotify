from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mopidy_spotify import utils

if TYPE_CHECKING:
    from pathlib import Path

CLIENT_ID = "f88ee52f92724d51b7579a1d1cdb3128"
REDIRECT_URI = "https://mopidy.com/auth/spotify"
SCOPES = (
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-follow-read",
    "user-library-read",
    "user-library-modify",
    "user-read-recently-played",
    "user-read-private",
    "user-top-read",
    "streaming",
)
AUTH_FILE_VERSION = 1


class AuthPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = AUTH_FILE_VERSION


class PkceAuthorizedAuthPayload(AuthPayloadBase):
    mode: Literal["pkce"] = "pkce"
    state: Literal["authorized"] = "authorized"
    refresh_token: str


class PkceRevokedAuthPayload(AuthPayloadBase):
    mode: Literal["pkce"] = "pkce"
    state: Literal["revoked"] = "revoked"


class BridgeConfiguredAuthPayload(AuthPayloadBase):
    mode: Literal["bridge"] = "bridge"
    state: Literal["configured"] = "configured"


class BridgeClearedAuthPayload(AuthPayloadBase):
    mode: Literal["bridge"] = "bridge"
    state: Literal["cleared"] = "cleared"


class BridgePermanentErrorAuthPayload(AuthPayloadBase):
    mode: Literal["bridge"] = "bridge"
    state: Literal["permanent_error"] = "permanent_error"
    error_code: str
    error_description: str | None = None


type AuthPayload = Annotated[
    PkceAuthorizedAuthPayload
    | PkceRevokedAuthPayload
    | BridgeConfiguredAuthPayload
    | BridgeClearedAuthPayload
    | BridgePermanentErrorAuthPayload,
    Field(discriminator="state"),
]
AUTH_PAYLOAD_ADAPTER = TypeAdapter(AuthPayload)


class InvalidRefreshTokenError(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizationResult:
    code: str
    state: str


@dataclass(frozen=True)
class FileAuthStateStore:
    path: Path

    def load(self) -> AuthPayload | None:
        if not self.path.exists():
            return None

        try:
            return AUTH_PAYLOAD_ADAPTER.validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (ValidationError, ValueError) as exc:
            msg = f"Invalid Spotify auth.json: {self.path}"
            raise InvalidRefreshTokenError(msg) from exc

    def save(self, payload: AuthPayload) -> None:
        content = payload.model_dump_json().encode("utf-8")
        with utils.replace(self.path, mode=0o600) as file_handle:
            file_handle.write(content)


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce_verifier() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_authorization_url(challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": " ".join(SCOPES),
        }
    )
    return f"https://accounts.spotify.com/authorize?{query}"


def parse_authorization_result(result: str) -> AuthorizationResult:
    result = result.strip()
    for parser in (
        _parse_authorization_url,
        _parse_base64_query_string,
    ):
        if parsed_result := parser(result):
            error = parsed_result.get("error")
            if error is not None:
                error_description = parsed_result.get("error_description")
                if error_description is None:
                    raise ValueError(error)

                msg = f"{error}: {error_description}"
                raise ValueError(msg)

            code = parsed_result.get("code")
            state = parsed_result.get("state")
            if code is None or state is None:
                msg = "missing code/state."
                raise ValueError(msg)

            return AuthorizationResult(code=code, state=state)

    msg = "invalid authorization response."
    raise ValueError(msg)


def _parse_authorization_url(result: str) -> dict[str, str] | None:
    parsed = urllib.parse.urlsplit(result)
    query = parsed.query or parsed.fragment
    if not query:
        return None

    return dict(urllib.parse.parse_qsl(query, keep_blank_values=True))


def _parse_base64_query_string(result: str) -> dict[str, str] | None:
    try:
        padded_result = result + "=" * (-len(result) % 4)
        decoded_result = base64.urlsafe_b64decode(padded_result).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    return dict(urllib.parse.parse_qsl(decoded_result, keep_blank_values=True))


def exchange_code_request(code: str, verifier: str) -> requests.Request:
    return requests.Request(
        "POST",
        "https://accounts.spotify.com/api/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )


def refresh_token_request(auth_state_path: Path) -> requests.Request:
    payload = FileAuthStateStore(auth_state_path).load()
    if payload is None:
        msg = "missing refresh_token"
        raise ValueError(msg)
    if payload.mode != "pkce":
        error = (
            "Spotify auth.json uses unsupported mode for refresh_token: "
            f"{auth_state_path} ({payload.mode})"
        )
        raise InvalidRefreshTokenError(error)
    if payload.state == "revoked":
        error = f"Spotify auth.json is revoked: {auth_state_path}"
        raise InvalidRefreshTokenError(error)
    return requests.Request(
        "POST",
        "https://accounts.spotify.com/api/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": payload.refresh_token,
        },
    )
