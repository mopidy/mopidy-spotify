import logging
import os
from pathlib import Path

from mopidy import commands

from mopidy_spotify import Extension

logger = logging.getLogger(__name__)


class SpotifyCommand(commands.Command):
    def __init__(self):
        super().__init__()
        self.add_child("logout", LogoutCommand())


class LogoutCommand(commands.Command):
    help = "Logout from Spotify account."

    def run(
        self,
        args,  # noqa: ARG002
        config,
    ):
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
