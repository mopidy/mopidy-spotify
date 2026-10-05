import json

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_core import PydanticSerializationError

from mopidy_spotify.oauth import credentials, manifest


@pytest.mark.parametrize("mode", ["bridge", "pkce"])
def test_legacy_error_manifests_remain_compatible(mode: str):
    content = {
        "version": 1,
        "mode": mode,
        "state": "permanent_error",
        "error_code": "invalid_grant",
    }
    value = manifest.validate_json(json.dumps(content))
    assert isinstance(value, manifest.PermanentError)
    assert value.credential_fingerprint is None
    assert "credential_fingerprint" not in json.loads(manifest.dump_json(value))


@pytest.mark.parametrize("description", [None, "Credentials rejected"])
def test_error_manifest_omits_absent_fields_and_preserves_round_trip(
    description: str | None,
):
    value = manifest.PermanentError(
        version=1,
        mode="bridge",
        error_code="invalid_client",
        error_description=description,
    )
    content = manifest.dump_json(value)
    saved = json.loads(content)
    assert "credential_fingerprint" not in saved
    if description is None:
        assert "error_description" not in saved
    else:
        assert saved["error_description"] == description
    assert manifest.validate_json(content.decode("utf-8")) == value


@pytest.mark.parametrize(
    "fingerprint", ["scrypt-v2$bad", "scrypt-v1$bad", "plain-secret"]
)
def test_error_manifest_rejects_invalid_fingerprint(fingerprint: str):
    with pytest.raises(ValidationError):
        manifest.PermanentError.model_validate(
            {
                "version": 1,
                "mode": "bridge",
                "error_code": "invalid_client",
                "credential_fingerprint": fingerprint,
            }
        )


def test_pkce_error_manifest_cannot_store_bridge_fingerprint():
    with pytest.raises(ValidationError, match="only to bridge"):
        manifest.PermanentError(
            version=1,
            mode="pkce",
            error_code="invalid_grant",
            credential_fingerprint=credentials.Fingerprint(
                f"scrypt-v1${'00' * 16}${'00' * 32}"
            ),
        )


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
