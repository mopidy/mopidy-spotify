"""Small facade over the optional system keyring dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["Error", "Store", "UnavailableError", "memory", "system"]


class Store(Protocol):
    """Store raw secret strings by key within a configured namespace."""

    def load(self, key: str) -> str | None:
        """Return the raw value, or ``None`` when ``key`` is absent."""
        ...

    def save(self, key: str, value: str) -> None:
        """Replace the raw value stored at ``key``."""
        ...

    def clear(self, key: str) -> None:
        """Remove ``key``, succeeding when it is already absent."""
        ...


class Error(Exception):
    """Raised when the keyring cannot complete an operation."""


class UnavailableError(Error):
    """Raised when the optional keyring backend is unavailable."""


def system(service: str) -> Store:
    """Return storage backed by the optional system keyring package."""
    try:
        import keyring as backend  # pyright: ignore[reportMissingImports]  # noqa: PLC0415
    except ImportError as exc:
        msg = "Keyring backend is unavailable"
        raise UnavailableError(msg) from exc
    return _System(service, backend)  # type: ignore[arg-type]


def memory() -> Store:
    """Return volatile storage intended for tests."""
    return _Memory()


# TODO: Add keyring.file(directory) when a concrete file-backed store is required.


class _Backend(Protocol):
    """Subset of the optional keyring module used by the facade."""

    def get_password(self, service: str, username: str) -> str | None:
        """Return the addressed password, or ``None`` when absent."""
        ...

    def set_password(self, service: str, username: str, password: str) -> None:
        """Replace the addressed password."""
        ...

    def delete_password(self, service: str, username: str) -> None:
        """Remove the addressed password."""
        ...


@dataclass(frozen=True)
class _System:
    """Facade over the optional system keyring package."""

    service: str
    backend: _Backend

    def load(self, key: str) -> str | None:
        """Load a raw secret string.

        Callers own any redacting wrapper and should apply it immediately.
        """
        try:
            value = self.backend.get_password(self.service, key)
        except Error:
            raise
        except Exception as exc:
            msg = f"Could not load keyring entry for {self.service}/{key}"
            raise Error(msg) from exc
        return value

    def save(self, key: str, value: str) -> None:
        """Save a raw secret string at this explicit storage sink."""
        try:
            self.backend.set_password(self.service, key, value)
        except Error:
            raise
        except Exception as exc:
            msg = f"Could not save keyring entry for {self.service}/{key}"
            raise Error(msg) from exc

    def clear(self, key: str) -> None:
        """Remove the addressed secret, succeeding when it is absent."""
        try:
            if self.backend.get_password(self.service, key) is not None:
                self.backend.delete_password(self.service, key)
        except Exception as exc:
            msg = f"Could not clear keyring entry for {self.service}/{key}"
            raise Error(msg) from exc


@dataclass
class _Memory:
    """Volatile keyring implementation intended for tests."""

    values: dict[str, str] = field(default_factory=dict)

    def load(self, key: str) -> str | None:
        return self.values.get(key)

    def save(self, key: str, value: str) -> None:
        self.values[key] = value

    def clear(self, key: str) -> None:
        self.values.pop(key, None)
