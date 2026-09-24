"""Persistence and transitions for Spotify Web authorization state."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never

from filelock import FileLock
from pydantic import SecretStr, ValidationError
from uuid_extension import uuid7

from mopidy_spotify._ext import atomic, keyring
from mopidy_spotify.oauth import manifest, state

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    """Resolved authorization paired with the manifest it was loaded from."""

    state: state.State
    manifest: manifest.Manifest


class InvalidManifestError(ValueError):
    """Raised when the persisted authorization manifest is invalid."""


class Error(Exception):
    """Raised when authorization persistence cannot complete."""


class MissingInlineRefreshTokenError(Error):
    """Raised when an inline descriptor contains no refresh token."""


class MissingKeyringRefreshTokenError(Error):
    """Raised when a keyring descriptor points to no refresh token."""


class Store:
    """Persist Web authorization and reject stale state transitions."""

    def __init__(
        self,
        path: Path,
        *,
        keyring_store: keyring.Store | None = None,
        generate_keyring_username: Callable[[], object] = uuid7,
    ) -> None:
        self.path = path
        self._keyring = keyring_store
        self._generate_keyring_username = generate_keyring_username

    def _keyring_store(self) -> keyring.Store:
        if self._keyring is None:
            self._keyring = keyring.system(manifest.KEYRING_SERVICE)
        return self._keyring

    @contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with FileLock(f"{self.path}.lock", mode=0o600):
                yield
        except OSError as exc:
            msg = f"Could not lock Spotify authorization state at {self.path}"
            raise Error(msg) from exc

    def _load_manifest(self) -> manifest.Manifest | None:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as exc:
            msg = f"Could not load Spotify authorization state at {self.path}"
            raise Error(msg) from exc

        try:
            return manifest.validate_json(content)
        except (ValidationError, ValueError):
            pass

        msg = f"Invalid Spotify authorization state at {self.path}"
        raise InvalidManifestError(msg)

    def _resolve(self, stored_manifest: manifest.Manifest) -> state.State:
        if isinstance(stored_manifest, manifest.PkceAuthorized):
            descriptor = stored_manifest.refresh_token
            if isinstance(descriptor, manifest.InlineDescriptor):
                refresh_token = descriptor.value
                if not refresh_token.get_secret_value():
                    msg = "Inline refresh token is missing"
                    raise MissingInlineRefreshTokenError(msg)
            else:
                # The generic keyring facade returns raw strings. Wrap the
                # secret immediately at this extension-owned source boundary.
                value = self._keyring_store().load(descriptor.username)
                if value is None:
                    msg = f"Keyring refresh token is missing: {descriptor.username}"
                    raise MissingKeyringRefreshTokenError(msg)
                refresh_token = SecretStr(value)
            return state.PkceAuthorized(refresh_token=refresh_token)
        if isinstance(stored_manifest, manifest.BridgeConfigured):
            return state.BridgeConfigured()
        if isinstance(stored_manifest, manifest.Cleared):
            return state.Cleared(mode=stored_manifest.mode)
        return state.PermanentError(
            mode=stored_manifest.mode,
            error_code=stored_manifest.error_code,
            error_description=stored_manifest.error_description,
        )

    def load(self) -> Snapshot | None:
        """Load and resolve the current authorization snapshot."""
        stored_manifest = self._load_manifest()
        if stored_manifest is None:
            return None
        return Snapshot(
            state=self._resolve(stored_manifest),
            manifest=stored_manifest,
        )

    def _write_manifest(self, value: manifest.Manifest) -> None:
        try:
            content = manifest.dump_json(value)
            atomic.write(self.path, content, mode=0o600)
        except OSError as exc:
            msg = f"Could not save Spotify authorization state at {self.path}"
            raise Error(msg) from exc

    def _clear_descriptor(
        self,
        descriptor: manifest.RefreshDescriptor,
        *,
        suppress_errors: bool,
    ) -> None:
        if isinstance(descriptor, manifest.InlineDescriptor):
            return
        try:
            self._keyring_store().clear(descriptor.username)
        except keyring.Error:
            if not suppress_errors:
                raise
            logger.warning(
                "Could not remove replaced Spotify %s refresh token",
                descriptor.storage,
                exc_info=True,
            )

    def _replace_manifest(
        self,
        replacement: manifest.Manifest,
        *,
        staged_descriptor: manifest.RefreshDescriptor | None = None,
        previous_manifest: manifest.Manifest | None = None,
        strict_cleanup: bool = False,
    ) -> None:
        try:
            self._write_manifest(replacement)
        except Exception:
            if staged_descriptor is not None:
                self._clear_descriptor(staged_descriptor, suppress_errors=True)
            raise

        next_descriptor = (
            replacement.refresh_token
            if isinstance(replacement, manifest.PkceAuthorized)
            else None
        )
        if (
            isinstance(previous_manifest, manifest.PkceAuthorized)
            and previous_manifest.refresh_token != next_descriptor
        ):
            self._clear_descriptor(
                previous_manifest.refresh_token,
                suppress_errors=not strict_cleanup,
            )

    def persist_pkce_authorization(
        self,
        token: SecretStr,
        storage_type: manifest.StorageType = manifest.StorageType.INLINE,
    ) -> None:
        """Persist successful PKCE authorization and retire any previous token."""
        with self._locked():
            try:
                previous_manifest = self._load_manifest()
            except InvalidManifestError:
                previous_manifest = None

            match storage_type:
                case manifest.StorageType.INLINE:
                    staged_descriptor = manifest.InlineDescriptor(value=token)
                case manifest.StorageType.KEYRING:
                    staged_descriptor = manifest.KeyringDescriptor(
                        username=str(self._generate_keyring_username())
                    )
                    self._keyring_store().save(
                        staged_descriptor.username,
                        token.get_secret_value(),
                    )
                case _:
                    assert_never(storage_type)
            self._replace_manifest(
                manifest.PkceAuthorized(
                    version=manifest.AUTH_FILE_VERSION,
                    refresh_token=staged_descriptor,
                ),
                staged_descriptor=staged_descriptor,
                previous_manifest=previous_manifest,
            )

    def compare_and_set(
        self,
        expected: Snapshot | None,
        next_state: state.State,
    ) -> bool:
        """Persist ``next_state`` only if the current manifest matches ``expected``."""
        with self._locked():
            current_manifest = self._load_manifest()
            expected_manifest = expected.manifest if expected is not None else None
            if current_manifest != expected_manifest:
                return False

            staged_descriptor = None
            match next_state:
                case state.PkceAuthorized():
                    if not isinstance(current_manifest, manifest.PkceAuthorized):
                        msg = "PKCE authorization has no current storage descriptor"
                        raise Error(msg)
                    if expected is not None and next_state == expected.state:
                        descriptor = current_manifest.refresh_token
                    elif isinstance(
                        current_manifest.refresh_token,
                        manifest.InlineDescriptor,
                    ):
                        descriptor = manifest.InlineDescriptor(
                            value=next_state.refresh_token
                        )
                    else:
                        staged_descriptor = manifest.KeyringDescriptor(
                            username=str(self._generate_keyring_username())
                        )
                        self._keyring_store().save(
                            staged_descriptor.username,
                            next_state.refresh_token.get_secret_value(),
                        )
                        descriptor = staged_descriptor
                    next_manifest: manifest.Manifest = manifest.PkceAuthorized(
                        version=manifest.AUTH_FILE_VERSION, refresh_token=descriptor
                    )
                case state.BridgeConfigured():
                    next_manifest = manifest.BridgeConfigured(
                        version=manifest.AUTH_FILE_VERSION
                    )
                case state.Cleared():
                    next_manifest = manifest.Cleared(
                        version=manifest.AUTH_FILE_VERSION,
                        mode=next_state.mode,
                    )
                case state.PermanentError():
                    next_manifest = manifest.PermanentError(
                        version=manifest.AUTH_FILE_VERSION,
                        mode=next_state.mode,
                        error_code=next_state.error_code,
                        error_description=next_state.error_description,
                    )
                case _:
                    assert_never(next_state)

            self._replace_manifest(
                next_manifest,
                staged_descriptor=staged_descriptor,
                previous_manifest=current_manifest,
            )
            return True

    def clear(self) -> None:
        """Persist intentional clearing and retire any external token."""
        with self._locked():
            try:
                previous_manifest = self._load_manifest()
            except InvalidManifestError:
                previous_manifest = None
            mode: Literal["pkce", "bridge"] = (
                previous_manifest.mode if previous_manifest is not None else "bridge"
            )
            self._replace_manifest(
                manifest.Cleared(
                    version=manifest.AUTH_FILE_VERSION,
                    mode=mode,
                ),
                previous_manifest=previous_manifest,
                strict_cleanup=True,
            )
