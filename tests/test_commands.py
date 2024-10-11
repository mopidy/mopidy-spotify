from unittest.mock import sentinel

from mopidy_spotify import Extension
from mopidy_spotify.commands import LogoutCommand


def test_logout_command(tmp_path):
    config = {"core": {"data_dir": tmp_path}}
    credentials_dir = Extension().get_credentials_dir(config)
    (credentials_dir / "foo").mkdir()
    (credentials_dir / "bar").touch()

    cmd = LogoutCommand()
    cmd.run(sentinel.args, config)

    assert not credentials_dir.is_dir()
