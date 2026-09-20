import errno
from pathlib import Path
from unittest import mock

import pytest

from mopidy_spotify._ext import atomic


def test_write_replaces_file_with_requested_mode(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_bytes(b"old-secret")

    atomic.write(target, b"new-secret", mode=0o640)

    assert target.read_bytes() == b"new-secret"
    assert target.stat().st_mode & 0o777 == 0o640


def test_replace_supports_streamed_writes(tmp_path: Path):
    target = tmp_path / "secret.txt"

    with atomic.replace(target, mode=0o600) as file_handle:
        file_handle.write(b"new-")
        file_handle.write(b"secret")

    assert target.read_bytes() == b"new-secret"


def test_replace_preserves_destination_after_write_error(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_bytes(b"old-secret")
    message = "boom"

    def write_then_fail() -> None:
        with atomic.replace(target) as file_handle:
            file_handle.write(b"new-secret")
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match=message):
        write_then_fail()

    assert target.read_bytes() == b"old-secret"
    assert list(tmp_path.iterdir()) == [target]


def test_replace_requires_existing_parent_directory(tmp_path: Path):
    target = tmp_path / "missing" / "secret.txt"

    with pytest.raises(FileNotFoundError), atomic.replace(target) as file_handle:
        file_handle.write(b"new-secret")


def test_write_succeeds_when_directory_sync_is_unsupported(tmp_path: Path):
    target = tmp_path / "secret.txt"
    unsupported = OSError(errno.ENOTSUP, "not supported")

    with mock.patch.object(atomic.os, "fsync", side_effect=[None, unsupported]):
        atomic.write(target, b"new-secret")

    assert target.read_bytes() == b"new-secret"


def test_write_reports_directory_sync_failure(tmp_path: Path):
    target = tmp_path / "secret.txt"
    failure = OSError(errno.EIO, "sync failed")

    with (
        mock.patch.object(atomic.os, "fsync", side_effect=[None, failure]),
        pytest.raises(OSError, match="sync failed"),
    ):
        atomic.write(target, b"new-secret")

    assert target.read_bytes() == b"new-secret"


def test_directory_sync_is_skipped_on_non_posix_platforms(tmp_path: Path):
    with (
        mock.patch.object(atomic.os, "name", "nt"),
        mock.patch.object(atomic.os, "open") as open_mock,
    ):
        atomic._sync_directory(tmp_path)

    open_mock.assert_not_called()
