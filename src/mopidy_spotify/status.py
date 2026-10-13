"""Describe saved Web and playback authorization for a Mopidy configuration.

The report inspects local credentials without contacting Spotify or changing
authorization. Each credential set is inspected independently, so a storage
failure does not hide the other status. Paths, provider eligibility, errors, and
display wording are owned here; callers only print the returned lines.
"""

from typing import assert_never

from mopidy.config import Config

from mopidy_spotify import Extension
from mopidy_spotify.oauth import providers, state, store

__all__ = ["describe"]


def describe(config: Config) -> tuple[str, str]:
    """Return Web and playback status lines without verifying access with Spotify."""
    return (
        f"Spotify Web API: {_web_status(config)}",
        f"Spotify playback: {_playback_status(config)}",
    )


def _web_status(config: Config) -> str:
    try:
        auth_store = store.Store(Extension.get_auth_state_path(config))
        spotify = config.get("spotify", {})
        bridge = providers.BridgeProvider(
            client_id=spotify.get("client_id"),
            client_secret=spotify.get("client_secret"),
        )
        return _describe_web_authorization(auth_store, bridge)
    except store.InvalidManifestError:
        return "invalid authorization state"
    except (store.Error, OSError) as exc:
        return f"unavailable ({exc})"


def _playback_status(config: Config) -> str:
    try:
        credentials_file = Extension.get_credentials_dir(config) / "credentials.json"
        return "stored" if credentials_file.is_file() else "not authorized"
    except OSError as exc:
        return f"unavailable ({exc})"


def _describe_web_authorization(
    auth_store: store.Store, bridge: providers.BridgeProvider
) -> str:
    snapshot = auth_store.load()
    auth_state = snapshot.state if snapshot is not None else None

    match auth_state:
        case state.PkceAuthorized():
            return "authorized (PKCE)"
        case None | state.Cleared() | state.BridgeConfigured():
            # These states all permit legacy authentication: missing or cleared
            # local authorization allows fallback; BridgeConfigured selects it
            # explicitly. None of these states supplies credentials, so report
            # configured only when the legacy provider can use the credentials
            # in Mopidy config; otherwise report not authorized.
            return (
                "configured (legacy)"
                if bridge.supports(auth_state)
                else "not authorized"
            )
        case state.PermanentError():
            # A legacy rejection blocks only the rejected credential pair.
            # Changed credentials, or an older rejection without a fingerprint,
            # permit retry; configured does not mean Spotify has accepted them.
            if bridge.supports(auth_state):
                return "configured (legacy)"
            match auth_state.mode:
                case "pkce":
                    return "PKCE authorization rejected"
                case "bridge":
                    return "legacy authorization rejected"
                case _:
                    assert_never(auth_state.mode)
        case _:
            assert_never(auth_state)
