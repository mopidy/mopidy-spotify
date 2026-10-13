import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import cyclopts
from mopidy.config import Config

from mopidy_spotify import Extension
from mopidy_spotify.oauth import flow, providers, state, store

logger = logging.getLogger(__name__)


app = cyclopts.App(help="Spotify extension commands.")
auth_app = cyclopts.App(
    name="auth",
    help="Authorize Spotify Web API and playback access.",
)
app.command(auth_app)


def run_auth_command(
    auth_flow: flow.AuthFlow,
    *,
    read_input: Callable[[], str] = input,
    write_output: Callable[..., None] = print,
) -> int:
    challenge = auth_flow.start_auth()

    write_output("Please visit the following URL:\n")
    write_output(challenge.authorization_url)
    write_output()
    write_output("After authorizing, paste the result shown in your browser here:\n")
    write_output()

    try:
        pasted_result = read_input()
    except EOFError:
        write_output("Authentication aborted.")
        return 1

    try:
        auth_flow.finish_auth(challenge, pasted_result)
    except flow.AuthFlowError as exc:
        write_output(str(exc))
        return 1

    write_output()
    write_output("Refresh token successfully stored.")
    return 0


@auth_app.command(help="Authorize Spotify Web API access.")
def web(
    *,
    storage: Annotated[
        flow.StoragePolicy,
        cyclopts.Parameter(
            help="Refresh-token storage: auto tries keyring and warns before "
            "falling back to plaintext; plaintext always uses a file; "
            "keyring never falls back."
        ),
    ] = flow.StoragePolicy.AUTO,
    legacy: Annotated[
        bool,
        cyclopts.Parameter(
            help="Use the legacy Mopidy authentication server with configured "
            "client_id and client_secret, replacing local authorization."
        ),
    ] = False,
) -> int:
    config = Config.get_global()
    if legacy:
        if storage != flow.StoragePolicy.AUTO:
            logger.error("--storage applies to local authorization, not --legacy.")
            return 1
        return _use_legacy_bridge(config)

    auth_state_path = Extension.get_auth_state_path(config)
    writer = flow.authorization_writer(store.Store(auth_state_path), storage)
    auth_flow = flow.AuthFlow(config, persist_authorization=writer)
    return run_auth_command(auth_flow)


@auth_app.command(help="Authorize librespot playback credentials.")
def playback() -> int:
    config = Config.get_global()
    helper = shutil.which("gstspotify-auth")
    if helper is None:
        logger.error(
            "Could not find gstspotify-auth. Install a gst-plugin-spotify "
            "package that includes the authentication helper."
        )
        return 1

    try:
        credentials_dir = Extension.get_credentials_dir(config)
        result = subprocess.run(  # noqa: S603
            [helper, os.fspath(credentials_dir)],
            check=False,
        )
    except OSError as exc:
        logger.warning("Could not run gstspotify-auth: %s", exc)
        return 1
    return result.returncode


@auth_app.command(help="Show Web API and playback authorization status.")
def status() -> None:
    for line in _status_lines(Config.get_global()):
        print(line)  # noqa: T201


@app.command(help="Logout from Spotify account.")
def logout() -> None:
    config = Config.get_global()

    credentials_cleared = True
    try:
        credentials_dir = Extension.get_credentials_dir(config)
        for root, dirs, files in os.walk(credentials_dir, topdown=False):
            root_path = Path(root)
            for name in files:
                file_path = root_path / name
                file_path.unlink()
                logger.debug(f"Removed file {file_path}")
            for name in dirs:
                dir_path = root_path / name
                dir_path.rmdir()
                logger.debug(f"Removed directory {dir_path}")
        credentials_dir.rmdir()
    except Exception as error:  # noqa: BLE001
        credentials_cleared = False
        logger.warning(f"Failed to clear Spotify playback credentials: {error}")

    auth_state_cleared = True
    try:
        auth_state_path = Extension.get_auth_state_path(config)
        store.Store(auth_state_path).clear()
        logger.debug(f"Cleared file {auth_state_path}")
    except Exception as error:  # noqa: BLE001
        auth_state_cleared = False
        logger.warning(f"Failed to clear Spotify authorization: {error}")

    if credentials_cleared and auth_state_cleared:
        logger.info("Logged out from Spotify")


def _web_status(config: Config) -> str:
    try:
        auth_store = store.Store(Extension.get_auth_state_path(config))
        snapshot = auth_store.load()
    except store.InvalidManifestError:
        return "invalid authorization state"
    except (store.Error, OSError) as exc:
        return f"unavailable ({exc})"

    spotify = config.get("spotify", {})
    bridge = providers.BridgeProvider(
        client_id=spotify.get("client_id"),
        client_secret=spotify.get("client_secret"),
    )
    auth_state = snapshot.state if snapshot is not None else None

    if isinstance(auth_state, state.PkceAuthorized):
        return "authorized (PKCE)"
    if bridge.supports(auth_state):
        return "configured (legacy bridge)"
    if isinstance(auth_state, state.PermanentError):
        return (
            "reauthorization required (legacy bridge)"
            if auth_state.mode == "bridge"
            else "reauthorization required"
        )
    return "not authorized"


def _status_lines(config: Config) -> tuple[str, str]:
    try:
        credentials_file = Extension.get_credentials_dir(config) / "credentials.json"
        playback_status = "stored" if credentials_file.is_file() else "not authorized"
    except OSError as exc:
        playback_status = f"unavailable ({exc})"
    return (
        f"Spotify Web API: {_web_status(config)}",
        f"Spotify playback: {playback_status}",
    )


def _use_legacy_bridge(config: Config) -> int:
    auth_state_path = Extension.get_auth_state_path(config)
    try:
        store.Store(auth_state_path).configure_bridge()
    except store.Error as exc:
        logger.warning(
            "Could not complete the switch to legacy authentication: %s", exc
        )
        return 1

    spotify_config = config.get("spotify", {})
    if not spotify_config.get("client_id") or not spotify_config.get("client_secret"):
        logger.warning(
            "Legacy authentication selected. Configure both spotify/client_id and "
            "spotify/client_secret before starting Mopidy. Playback credentials "
            "are unchanged."
        )
    else:
        logger.info(
            "Legacy authentication selected for the next token refresh. "
            "Playback credentials are unchanged."
        )
    return 0
