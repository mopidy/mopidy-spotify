import json
from pathlib import Path
from unittest import mock

import pytest
from pydantic import SecretStr

from mopidy_spotify._ext import keyring as keyring_ext
from mopidy_spotify.oauth import manifest, state
from mopidy_spotify.oauth import store as auth_store


def test_store_returns_none_for_missing_file(tmp_path: Path):
    assert auth_store.Store(tmp_path / "auth.json").load() is None


def test_store_reports_unreadable_manifest_as_io_failure(tmp_path: Path):
    path = tmp_path / "auth.json"
    with (
        mock.patch.object(Path, "read_text", side_effect=PermissionError),
        pytest.raises(auth_store.Error, match="Could not load"),
    ):
        auth_store.Store(path).load()


def test_store_reports_lock_directory_failure(tmp_path: Path):
    path = tmp_path / "auth.json"
    with (
        mock.patch.object(Path, "mkdir", side_effect=PermissionError),
        pytest.raises(auth_store.Error, match="Could not lock"),
    ):
        auth_store.Store(path).persist_pkce_authorization(SecretStr("refresh-token"))

    assert not path.exists()


def test_store_round_trips_inline_authorization(tmp_path: Path):
    path = tmp_path / "auth.json"
    store = auth_store.Store(path)

    store.persist_pkce_authorization(SecretStr("refresh-token"))

    snapshot = store.load()
    assert snapshot is not None
    assert snapshot.state == state.PkceAuthorized(
        refresh_token=SecretStr("refresh-token")
    )
    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {"storage": "inline", "value": "refresh-token"},
    }


def test_inline_authorization_does_not_initialize_keyring(tmp_path: Path):
    store = auth_store.Store(tmp_path / "auth.json")

    with mock.patch.object(
        keyring_ext,
        "system",
        side_effect=AssertionError("keyring should stay lazy"),
    ):
        store.persist_pkce_authorization(SecretStr("refresh-token"))
        assert store.load() is not None


def test_store_round_trips_keyring_authorization(tmp_path: Path):
    path = tmp_path / "auth.json"
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        path,
        keyring_store=keyring,
        generate_keyring_username=lambda: "token-id",
    )

    store.persist_pkce_authorization(
        SecretStr("refresh-token"), manifest.StorageType.KEYRING
    )

    snapshot = store.load()
    assert snapshot is not None
    assert snapshot.state == state.PkceAuthorized(
        refresh_token=SecretStr("refresh-token")
    )
    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {
            "storage": "keyring",
            "service": "mopidy-spotify",
            "username": "token-id",
        },
    }
    assert keyring.values == {"token-id": "refresh-token"}


def test_store_rejects_greenfield_raw_token_shape(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        '{"version":1,"mode":"pkce","state":"authorized","refresh_token":"old-shape"}'
    )

    with pytest.raises(auth_store.InvalidManifestError):
        auth_store.Store(path).load()


def test_store_does_not_chain_invalid_manifest(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text('{"refresh_token":{"storage":"inline","value":"secret"}}')

    with pytest.raises(auth_store.InvalidManifestError) as exc_info:
        auth_store.Store(path).load()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_pkce_authorization_replaces_invalid_manifest(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text("not-json")
    store = auth_store.Store(path)

    store.persist_pkce_authorization(SecretStr("refresh-token"))

    snapshot = store.load()
    assert snapshot is not None
    assert snapshot.state == state.PkceAuthorized(
        refresh_token=SecretStr("refresh-token")
    )


def test_missing_keyring_entry_is_distinct_from_invalid_manifest(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "pkce",
                "state": "authorized",
                "refresh_token": {
                    "storage": "keyring",
                    "service": "mopidy-spotify",
                    "username": "missing",
                },
            }
        )
    )

    with pytest.raises(auth_store.MissingKeyringRefreshTokenError):
        auth_store.Store(path, keyring_store=keyring_ext.memory()).load()


def test_missing_inline_value_is_distinct_from_invalid_manifest(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "pkce",
                "state": "authorized",
                "refresh_token": {"storage": "inline", "value": ""},
            }
        )
    )

    with pytest.raises(auth_store.MissingInlineRefreshTokenError, match="Inline"):
        auth_store.Store(path).load()


def test_keyring_descriptor_does_not_fall_back_to_inline_storage(tmp_path: Path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "pkce",
                "state": "authorized",
                "refresh_token": {
                    "storage": "keyring",
                    "service": "mopidy-spotify",
                    "username": "missing",
                },
            }
        )
    )

    with (
        mock.patch.dict("sys.modules", {"keyring": None}),
        pytest.raises(keyring_ext.UnavailableError),
    ):
        auth_store.Store(path).load()


def test_rotated_keyring_token_uses_fresh_address_and_clears_old(tmp_path: Path):
    usernames = iter(["first", "second"])
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        tmp_path / "auth.json",
        keyring_store=keyring,
        generate_keyring_username=lambda: next(usernames),
    )
    store.persist_pkce_authorization(
        SecretStr("original"), manifest.StorageType.KEYRING
    )
    snapshot = store.load()
    assert snapshot is not None

    assert store.compare_and_set(
        snapshot,
        state.PkceAuthorized(refresh_token=SecretStr("rotated")),
    )

    assert keyring.values == {"second": "rotated"}


def test_keyring_cleanup_failure_does_not_rollback_rotation(tmp_path: Path):
    path = tmp_path / "auth.json"
    usernames = iter(["first", "second"])
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        path,
        keyring_store=keyring,
        generate_keyring_username=lambda: next(usernames),
    )
    store.persist_pkce_authorization(
        SecretStr("original"), manifest.StorageType.KEYRING
    )

    with mock.patch.object(
        keyring,
        "clear",
        side_effect=keyring_ext.Error("cleanup failed"),
    ):
        store.persist_pkce_authorization(
            SecretStr("replacement"), manifest.StorageType.KEYRING
        )

    assert json.loads(path.read_text())["refresh_token"]["username"] == "second"
    assert keyring.values == {"first": "original", "second": "replacement"}


def test_unchanged_keyring_token_preserves_existing_address(tmp_path: Path):
    usernames = iter(["first"])
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        tmp_path / "auth.json",
        keyring_store=keyring,
        generate_keyring_username=lambda: next(usernames),
    )
    store.persist_pkce_authorization(
        SecretStr("refresh-token"), manifest.StorageType.KEYRING
    )
    snapshot = store.load()
    assert snapshot is not None

    assert store.compare_and_set(snapshot, snapshot.state)

    assert keyring.values == {"first": "refresh-token"}


def test_rotated_inline_token_replaces_manifest_value(tmp_path: Path):
    path = tmp_path / "auth.json"
    store = auth_store.Store(path)
    store.persist_pkce_authorization(SecretStr("original"))
    snapshot = store.load()
    assert snapshot is not None

    assert store.compare_and_set(
        snapshot,
        state.PkceAuthorized(refresh_token=SecretStr("rotated")),
    )

    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {"storage": "inline", "value": "rotated"},
    }


def test_compare_and_set_requires_existing_pkce_descriptor(tmp_path: Path):
    store = auth_store.Store(tmp_path / "auth.json")

    with pytest.raises(auth_store.Error, match="no current storage descriptor"):
        store.compare_and_set(
            None,
            state.PkceAuthorized(refresh_token=SecretStr("refresh-token")),
        )

    assert store.load() is None


def test_stale_keyring_rotation_does_not_create_staged_descriptor(tmp_path: Path):
    usernames = iter(["first", "replacement", "stale-staged-entry"])
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        tmp_path / "auth.json",
        keyring_store=keyring,
        generate_keyring_username=lambda: next(usernames),
    )
    store.persist_pkce_authorization(
        SecretStr("original"), manifest.StorageType.KEYRING
    )
    stale = store.load()
    assert stale is not None
    store.persist_pkce_authorization(
        SecretStr("replacement"), manifest.StorageType.KEYRING
    )

    assert not store.compare_and_set(
        stale,
        state.PkceAuthorized(refresh_token=SecretStr("rotated")),
    )
    assert "stale-staged-entry" not in keyring.values


def test_failed_manifest_update_removes_staged_keyring_descriptor(tmp_path: Path):
    usernames = iter(["first", "staged-entry"])
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        tmp_path / "auth.json",
        keyring_store=keyring,
        generate_keyring_username=lambda: next(usernames),
    )
    store.persist_pkce_authorization(
        SecretStr("original"), manifest.StorageType.KEYRING
    )
    snapshot = store.load()
    assert snapshot is not None

    with (
        mock.patch.object(auth_store.atomic, "write", side_effect=OSError),
        pytest.raises(auth_store.Error),
    ):
        store.compare_and_set(
            snapshot,
            state.PkceAuthorized(refresh_token=SecretStr("rotated")),
        )

    assert keyring.values == {"first": "original"}


@pytest.mark.parametrize(
    ("next_state", "expected_manifest"),
    [
        (
            state.BridgeConfigured(),
            {"version": 1, "mode": "bridge", "state": "configured"},
        ),
        (
            state.Cleared(mode="pkce"),
            {"version": 1, "mode": "pkce", "state": "cleared"},
        ),
        (
            state.PermanentError(
                mode="pkce",
                error_code="invalid_grant",
                error_description="Refresh token expired",
            ),
            {
                "version": 1,
                "mode": "pkce",
                "state": "permanent_error",
                "error_code": "invalid_grant",
                "error_description": "Refresh token expired",
            },
        ),
    ],
)
def test_compare_and_set_persists_resolved_state(
    tmp_path: Path,
    next_state: state.State,
    expected_manifest: dict[str, object],
):
    path = tmp_path / "auth.json"
    store = auth_store.Store(path)
    store.persist_pkce_authorization(SecretStr("refresh-token"))
    snapshot = store.load()
    assert snapshot is not None

    assert store.compare_and_set(snapshot, next_state)

    persisted = store.load()
    assert persisted is not None
    assert persisted.state == next_state
    assert json.loads(path.read_text()) == expected_manifest


def test_clear_removes_keyring_token_and_persists_cleared_state(tmp_path: Path):
    keyring = keyring_ext.memory()
    path = tmp_path / "auth.json"
    store = auth_store.Store(
        path,
        keyring_store=keyring,
        generate_keyring_username=lambda: "token-id",
    )
    store.persist_pkce_authorization(
        SecretStr("refresh-token"), manifest.StorageType.KEYRING
    )

    store.clear()

    assert keyring.values == {}
    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "pkce",
        "state": "cleared",
    }


def test_clear_reports_keyring_cleanup_failure_after_persisting_cleared_state(
    tmp_path: Path,
):
    path = tmp_path / "auth.json"
    keyring = keyring_ext.memory()
    store = auth_store.Store(
        path,
        keyring_store=keyring,
        generate_keyring_username=lambda: "token-id",
    )
    store.persist_pkce_authorization(
        SecretStr("refresh-token"), manifest.StorageType.KEYRING
    )

    with (
        mock.patch.object(keyring, "clear", side_effect=keyring_ext.Error),
        pytest.raises(keyring_ext.Error),
    ):
        store.clear()

    assert store.load() == auth_store.Snapshot(
        state=state.Cleared(mode="pkce"),
        manifest=manifest.Cleared(version=manifest.AUTH_FILE_VERSION, mode="pkce"),
    )
    assert keyring.values == {"token-id": "refresh-token"}
