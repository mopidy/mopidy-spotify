"""Describe saved Web and playback authorization for a Mopidy configuration.

The report inspects local credentials without contacting Spotify or changing
authorization. Each credential set is inspected independently, so a storage
failure does not hide the other status. This module owns configuration and playback
inspection; the Web authorization owner supplies its own status. Callers only
print the returned lines.
"""

from mopidy.config import Config

from mopidy_spotify import Extension
from mopidy_spotify.oauth import providers, store
from mopidy_spotify.oauth.source import SpotifyAccessTokenSource

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
        authorization = SpotifyAccessTokenSource(
            auth_store=auth_store,
            pkce=providers.PkceProvider(),
            bridge=providers.BridgeProvider(
                client_id=spotify.get("client_id"),
                client_secret=spotify.get("client_secret"),
            ),
        )
        return authorization.status()
    except OSError as exc:
        return f"unavailable ({exc})"


def _playback_status(config: Config) -> str:
    try:
        credentials_file = Extension.get_credentials_dir(config) / "credentials.json"
        return "stored" if credentials_file.is_file() else "not authorized"
    except OSError as exc:
        return f"unavailable ({exc})"
