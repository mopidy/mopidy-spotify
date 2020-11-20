import re

from mopidy_spotify import utils


def test_time_logger(caplog):
    with utils.time_logger("task"):
        pass

    assert re.match(r".*task took \d+ms.*", caplog.text)


def test_diff_op_repr():
    o0 = utils.op("+", ["1"], 1, 2)
    o1 = utils.op("+", ["1", "2", "3"], 1, 2)
    o2 = utils.op("-", ["1", "2", "3"], 1, 2)
    o3 = utils.op("m", ["1", "2", "3"], 1, 2)
    assert str(o0) == "<insert 1 tracks [1] at 1>"
    assert str(o1) == "<insert 3 tracks [1...3] at 1>"
    assert str(o2) == "<delete 3 tracks [1...3] at 1>"
    assert str(o3) == "<move 3 tracks [1...3] at 1 to 2>"
