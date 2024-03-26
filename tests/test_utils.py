import re
from unittest import mock

from mopidy_spotify import utils


def test_time_logger(caplog):
    with utils.time_logger("task"):
        pass

    assert re.match(r".*task took \d+ms.*", caplog.text)


def test_group_by_type():
    mocks = [mock.Mock(type=i % 3) for i in range(10)]

    types = []
    groups = []
    for mock_type, mock_group in utils.group_by_type(mocks):
        types.append(mock_type)
        groups.append(list(mock_group))

    assert types == [0, 1, 2]
    assert groups == [
        [mocks[0], mocks[3], mocks[6], mocks[9]],
        [mocks[1], mocks[4], mocks[7]],
        [mocks[2], mocks[5], mocks[8]],
    ]


def test_group_by_type_sorts():
    mocks = [
        mock.Mock(type="foo"),
        mock.Mock(type="bar"),
        None,
        mock.Mock(type="foo"),
        mock.Mock(type="baz"),
    ]

    types = []
    groups = []
    for mock_type, mock_group in utils.group_by_type(mocks):
        types.append(mock_type)
        groups.append(list(mock_group))

    assert types == ["bar", "baz", "foo"]
    assert groups == [
        [mocks[1]],
        [mocks[4]],
        [mocks[0], mocks[3]],
    ]


def test_batched():
    result = list(utils.batched("ABCDEFG", 3))
    assert result == [("A", "B", "C"), ("D", "E", "F"), ("G",)]
