"""Resolved runtime states for Spotify Web authorization.

These DTOs are exposed by :mod:`mopidy_spotify.oauth.store` after it resolves a
persisted manifest. In particular, authorized PKCE state contains a redacted
``SecretStr`` rather than an inline value or keyring address.

Refresh providers consume these states and return proposed next states. They do
not depend on the persisted manifest schema or external secret backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr


class PkceAuthorized(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    refresh_token: SecretStr
    mode: Literal["pkce"] = "pkce"
    state: Literal["authorized"] = "authorized"


@dataclass(frozen=True)
class BridgeConfigured:
    mode: Literal["bridge"] = "bridge"
    state: Literal["configured"] = "configured"


@dataclass(frozen=True)
class Cleared:
    mode: Literal["pkce", "bridge"]
    state: Literal["cleared"] = "cleared"


@dataclass(frozen=True)
class PermanentError:
    mode: Literal["pkce", "bridge"]
    error_code: str
    error_description: str | None = None
    state: Literal["permanent_error"] = "permanent_error"


type State = PkceAuthorized | BridgeConfigured | Cleared | PermanentError
