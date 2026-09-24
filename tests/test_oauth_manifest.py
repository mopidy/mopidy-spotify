import json

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_core import PydanticSerializationError

from mopidy_spotify.oauth import manifest


def test_inline_secret_requires_explicit_manifest_sink():
    value = manifest.PkceAuthorized(
        version=manifest.AUTH_FILE_VERSION,
        refresh_token=manifest.InlineDescriptor(value=SecretStr("refresh-token")),
    )

    with pytest.raises(PydanticSerializationError, match="manifest sink"):
        value.model_dump_json()

    assert json.loads(manifest.dump_json(value)) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {"storage": "inline", "value": "refresh-token"},
    }


def test_keyring_descriptor_contains_no_secret():
    value = manifest.PkceAuthorized(
        version=manifest.AUTH_FILE_VERSION,
        refresh_token=manifest.KeyringDescriptor(username="token-id"),
    )

    assert json.loads(manifest.dump_json(value)) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {
            "storage": "keyring",
            "service": "mopidy-spotify",
            "username": "token-id",
        },
    }


def test_validate_json_restores_redacted_inline_secret():
    value = manifest.validate_json(
        '{"version":1,"mode":"pkce","state":"authorized",'
        '"refresh_token":{"storage":"inline","value":"refresh-token"}}'
    )

    assert "refresh-token" not in repr(value)


def test_validate_json_rejects_manifest_without_version():
    with pytest.raises(ValidationError):
        manifest.validate_json(
            '{"mode":"pkce","state":"authorized",'
            '"refresh_token":{"storage":"inline","value":"refresh-token"}}'
        )
