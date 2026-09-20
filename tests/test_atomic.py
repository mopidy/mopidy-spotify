from pathlib import Path

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
