import re
from pathlib import Path
from unittest import mock

import pytest

from mopidy_spotify import utils


def test_time_logger(caplog: pytest.LogCaptureFixture):
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


def test_replace(tmp_path: Path):
    target = tmp_path / "refresh-token.txt"
    target.write_text("old-token")

    with utils.replace(target, mode=0o600) as file_handle:
        file_handle.write(b"new-token")

    assert target.read_text() == "new-token"
    assert target.stat().st_mode & 0o777 == 0o600


def test_replace_without_mode_keeps_tempfile_mode(tmp_path: Path):
    target = tmp_path / "refresh-token.txt"

    with utils.replace(target) as file_handle:
        file_handle.write(b"new-token")

    assert target.read_text() == "new-token"
    assert target.stat().st_mode & 0o777 == 0o600


def test_replace_requires_existing_parent_directory(tmp_path: Path):
    target = tmp_path / "missing" / "refresh-token.txt"

    with pytest.raises(FileNotFoundError), utils.replace(target) as file_handle:
        file_handle.write(b"new-token")


def test_replace_cleans_up_tempfile_after_write_error(tmp_path: Path):
    target = tmp_path / "refresh-token.txt"
    message = "boom"

    def write_then_fail() -> None:
        with utils.replace(target) as file_handle:
            file_handle.write(b"new-token")
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match=message):
        write_then_fail()

    assert list(tmp_path.iterdir()) == []
