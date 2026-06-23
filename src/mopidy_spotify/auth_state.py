from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mopidy_spotify import utils
from mopidy_spotify.pkce import CLIENT_ID

if TYPE_CHECKING:
    from pathlib import Path

AUTH_FILE_VERSION = 1


class AuthPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = AUTH_FILE_VERSION


class PkceAuthorizedAuthPayload(AuthPayloadBase):
    mode: Literal["pkce"] = "pkce"
    state: Literal["authorized"] = "authorized"
    refresh_token: str


class BridgeConfiguredAuthPayload(AuthPayloadBase):
    mode: Literal["bridge"] = "bridge"
    state: Literal["configured"] = "configured"


class ClearedAuthPayload(AuthPayloadBase):
    mode: Literal["pkce", "bridge"]
    state: Literal["cleared"] = "cleared"


class PermanentErrorAuthPayload(AuthPayloadBase):
    mode: Literal["pkce", "bridge"]
    state: Literal["permanent_error"] = "permanent_error"
    error_code: str
    error_description: str | None = None


type AuthPayload = Annotated[
    PkceAuthorizedAuthPayload
    | BridgeConfiguredAuthPayload
    | ClearedAuthPayload
    | PermanentErrorAuthPayload,
    Field(discriminator="state"),
]
AUTH_PAYLOAD_ADAPTER = TypeAdapter(AuthPayload)


class InvalidRefreshTokenError(ValueError):
    pass


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


def refresh_token_request(auth_state_path: Path) -> requests.Request:
    payload = FileAuthStateStore(auth_state_path).load()
    if payload is None:
        msg = "missing refresh_token"
        raise ValueError(msg)
    if payload.state != "authorized" or payload.mode != "pkce":
        error = (
            "Spotify auth.json uses unsupported state for refresh_token: "
            f"{auth_state_path} ({payload.mode}/{payload.state})"
        )
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
