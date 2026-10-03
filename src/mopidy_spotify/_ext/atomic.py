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
        # Some filesystems do not support directory synchronization. Ignore
        # only those cases; other failures may indicate lost durability.
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
        # Keep the temporary file beside the destination so replacement stays
        # on one filesystem and can be atomic.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as file_handle:
            temp_path = Path(file_handle.name)
            # Apply permissions before the new content can become authoritative.
            if mode is not None:
                os.fchmod(file_handle.fileno(), mode)

            yield cast("BinaryIO", file_handle)

            # Persist complete content before publishing the temporary file.
            file_handle.flush()
            os.fsync(file_handle.fileno())

        # The closed file atomically replaces the directory entry, so readers
        # observe either the previous complete file or the new complete file.
        temp_path.replace(path)
        # Persist the directory-entry change so replacement survives a crash.
        _sync_directory(path.parent)
    finally:
        if temp_path is not None:
            # Remove a leftover after failure; successful replacement already
            # consumed the temporary path.
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
