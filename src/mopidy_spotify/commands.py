import logging
import os
from collections.abc import Callable
from pathlib import Path

import cyclopts
from mopidy.config import Config

from mopidy_spotify import Extension, auth_flow, auth_state

logger = logging.getLogger(__name__)


app = cyclopts.App(help="Spotify extension commands.")


def run_auth_command(
    flow: auth_flow.AuthFlow,
    *,
    read_input: Callable[[], str] = input,
    write_output: Callable[..., None] = print,
) -> int:
    challenge = flow.start_auth()

    write_output(
        "Please visit the following URL. After authorizing, paste the result "
        "shown in your browser here:\n"
    )
    write_output(challenge.authorization_url)
    write_output()

    try:
        pasted_result = read_input()
    except EOFError:
        write_output("Authentication aborted.")
        return 1

    try:
        flow.finish_auth(challenge, pasted_result)
    except auth_flow.AuthFlowError as exc:
        write_output(str(exc))
        return 1

    write_output("Refresh token successfully stored.")
    return 0


@app.command(help="Store Spotify PKCE authorization.")
def auth() -> int:
    config = Config.get_global()
    auth_state_path = Extension.get_auth_state_path(config)
    flow = auth_flow.AuthFlow(config, auth_state_path)
    return run_auth_command(flow)


@app.command(help="Logout from Spotify account.")
def logout() -> None:
    config = Config.get_global()
    credentials_dir = Extension().get_credentials_dir(config)
    auth_state_path = Extension.get_auth_state_path(config)
    try:
        try:
            payload = auth_state.FileAuthStateStore(auth_state_path).load()
        except auth_state.InvalidRefreshTokenError:
            payload = None
        mode = payload.mode if payload is not None else "bridge"
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
        auth_state.FileAuthStateStore(auth_state_path).save(
            auth_state.ClearedAuthPayload(mode=mode)
        )
        logger.debug(f"Cleared file {auth_state_path}")
    except Exception as error:  # noqa: BLE001
        logger.warning(f"Failed to logout from Spotify: {error}")
    else:
        logger.info("Logged out from Spotify")
