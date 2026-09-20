"""Durable binary file replacement without concurrency control.

Replacement prevents readers from observing partial content. It does not stop
multiple writers from replacing each other's complete files; callers that need
conditional updates must serialize that higher-level transition separately.
"""

from __future__ import annotations

import contextlib
import errno
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, cast

if TYPE_CHECKING:
    from collections.abc import Iterator


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
            raise
    finally:
        os.close(directory_fd)


@contextmanager
def replace(
    path: Path,
    *,
    mode: int | None = None,
) -> Iterator[BinaryIO]:
    """Yield a temporary binary file and atomically replace ``path`` on success.

    The destination's parent directory must already exist. Content and the
    containing directory are synchronized before returning. If the context
    exits with an exception, the destination is unchanged and the temporary
    file is removed.
    """
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as file_handle:
            temp_path = Path(file_handle.name)
            if mode is not None:
                os.fchmod(file_handle.fileno(), mode)

            yield cast("BinaryIO", file_handle)

            file_handle.flush()
            os.fsync(file_handle.fileno())

        temp_path.replace(path)
        _sync_directory(path.parent)
    finally:
        if temp_path is not None:
            with contextlib.suppress(FileNotFoundError):
                temp_path.unlink()


def write(
    path: Path,
    content: bytes,
    *,
    mode: int | None = None,
) -> None:
    """Atomically replace ``path`` with complete binary ``content``."""
    with replace(path, mode=mode) as file_handle:
        file_handle.write(content)
