import logging
import os
from pathlib import Path

import cyclopts
from mopidy.config import Config

from mopidy_spotify import Extension

logger = logging.getLogger(__name__)


app = cyclopts.App(help="Spotify extension commands.")


@app.command(help="Logout from Spotify account.")
def logout():
    config = Config.get_global()
    credentials_dir = Extension().get_credentials_dir(config)
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
        logger.warning(f"Failed to logout from Spotify: {error}")
    else:
        logger.info("Logged out from Spotify")
