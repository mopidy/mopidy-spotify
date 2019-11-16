import re

from mopidy_spotify import utils


def test_time_logger(caplog):
    with utils.time_logger("task"):
        pass

    assert re.match(r".*task took \d+ms.*", caplog.text)
