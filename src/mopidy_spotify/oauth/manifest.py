"""Persisted schema for Spotify Web authorization.

The manifest is the authoritative JSON representation stored in ``auth.json``.
It records the authorization mode and lifecycle state, but PKCE refresh tokens
are represented by inline or keyring descriptors rather than a resolved runtime
secret.

Use :func:`validate_json` to parse persisted content and :func:`dump_json` to
serialize it. The explicit dump function is the only serialization path allowed
to unwrap an inline ``SecretStr``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    SerializationInfo,
    TypeAdapter,
    field_serializer,
)

AUTH_FILE_VERSION = 1
KEYRING_SERVICE = "mopidy-spotify"
_SECRET_SERIALIZATION_PASSKEY = object()


class StorageType(StrEnum):
    INLINE = "inline"
    KEYRING = "keyring"


class InlineDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage: Literal["inline"] = "inline"
    value: SecretStr

    @field_serializer("value", when_used="json")
    def serialize_value(
        self,
        value: SecretStr,
        info: SerializationInfo,
    ) -> str:
        if info.context is not _SECRET_SERIALIZATION_PASSKEY:
            msg = "Inline secret serialization requires the manifest sink"
            raise ValueError(msg)
        return value.get_secret_value()


class KeyringDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage: Literal["keyring"] = "keyring"
    service: Literal["mopidy-spotify"] = KEYRING_SERVICE
    username: str


type RefreshDescriptor = Annotated[
    InlineDescriptor | KeyringDescriptor,
    Field(discriminator="storage"),
]


class _ManifestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A default would also let persisted JSON omit the schema version.
    version: Literal[1]


class PkceAuthorized(_ManifestBase):
    mode: Literal["pkce"] = "pkce"
    state: Literal["authorized"] = "authorized"
    refresh_token: RefreshDescriptor


class BridgeConfigured(_ManifestBase):
    mode: Literal["bridge"] = "bridge"
    state: Literal["configured"] = "configured"


class Cleared(_ManifestBase):
    mode: Literal["pkce", "bridge"]
    state: Literal["cleared"] = "cleared"


class PermanentError(_ManifestBase):
    mode: Literal["pkce", "bridge"]
    state: Literal["permanent_error"] = "permanent_error"
    error_code: str
    error_description: str | None = None


type Manifest = Annotated[
    PkceAuthorized | BridgeConfigured | Cleared | PermanentError,
    Field(discriminator="state"),
]
_ADAPTER = TypeAdapter(Manifest)


def validate_json(content: str) -> Manifest:
    """Parse and validate a persisted authorization manifest."""
    return _ADAPTER.validate_json(content)


def dump_json(value: Manifest) -> bytes:
    """Serialize a manifest, unwrapping inline secrets at this explicit sink."""
    return _ADAPTER.dump_json(value, context=_SECRET_SERIALIZATION_PASSKEY)
