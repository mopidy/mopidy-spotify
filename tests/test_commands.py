from mopidy.config import Config

from mopidy_spotify import Extension
from mopidy_spotify.commands import logout


def test_logout_command(tmp_path):
    config = Config({"core": {"data_dir": tmp_path}})
    Config.set_global(config)

    credentials_dir = Extension().get_credentials_dir(config)
    (credentials_dir / "foo").mkdir()
    (credentials_dir / "bar").touch()

    logout()

    assert not credentials_dir.is_dir()
