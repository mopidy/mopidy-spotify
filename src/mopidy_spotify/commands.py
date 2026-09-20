import logging
import os
from collections.abc import Callable
from pathlib import Path

import cyclopts
from mopidy.config import Config

from mopidy_spotify import Extension
from mopidy_spotify.oauth import flow, manifest, store

logger = logging.getLogger(__name__)


app = cyclopts.App(help="Spotify extension commands.")
auth_app = cyclopts.App(
    name="auth",
    help="Authorize Spotify access.",
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


@auth_app.command(help="Authorize Spotify Web API access with PKCE.")
def web(
    *,
    storage: manifest.StorageType = manifest.StorageType.INLINE,
) -> int:
    config = Config.get_global()
    auth_state_path = Extension.get_auth_state_path(config)
    auth_flow = flow.AuthFlow(config, auth_state_path, storage_type=storage)
    return run_auth_command(auth_flow)


@app.command(help="Logout from Spotify account.")
def logout() -> None:
    config = Config.get_global()
    credentials_dir = Extension.get_credentials_dir(config)
    auth_state_path = Extension.get_auth_state_path(config)

    credentials_cleared = True
    try:
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
        store.Store(auth_state_path).clear()
        logger.debug(f"Cleared file {auth_state_path}")
    except Exception as error:  # noqa: BLE001
        auth_state_cleared = False
        logger.warning(f"Failed to clear Spotify authorization: {error}")

    if credentials_cleared and auth_state_cleared:
        logger.info("Logged out from Spotify")
