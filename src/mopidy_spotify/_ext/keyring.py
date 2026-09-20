"""Small facade over the optional system keyring dependency."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["Error", "Store", "UnavailableError", "memory", "system"]


class Error(Exception):
    """Raised when the keyring cannot complete an operation."""


class UnavailableError(Error):
    """Raised when the optional keyring backend is unavailable."""


class Store(Protocol):
    """Store raw secret strings by key within a configured namespace."""

    def load(self, key: str) -> str | None: ...

    def save(self, key: str, value: str) -> None: ...

    def clear(self, key: str) -> None: ...


class _Backend(Protocol):
    """Subset of the optional keyring module used by the facade."""

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


@dataclass(frozen=True)
class _System:
    """Facade over the optional system keyring package."""

    service: str

    def _backend(self) -> _Backend:
        try:
            return importlib.import_module("keyring")  # type: ignore[return-value]
        except ImportError as exc:
            msg = "Keyring backend is unavailable"
            raise UnavailableError(msg) from exc

    def load(self, key: str) -> str | None:
        """Load a raw secret string.

        Callers own any redacting wrapper and should apply it immediately.
        """
        try:
            value = self._backend().get_password(self.service, key)
        except Error:
            raise
        except Exception as exc:
            msg = f"Could not load keyring entry for {self.service}/{key}"
            raise Error(msg) from exc
        return value

    def save(self, key: str, value: str) -> None:
        """Save a raw secret string at this explicit storage sink."""
        try:
            self._backend().set_password(self.service, key, value)
        except Error:
            raise
        except Exception as exc:
            msg = f"Could not save keyring entry for {self.service}/{key}"
            raise Error(msg) from exc

    def clear(self, key: str) -> None:
        """Remove the addressed secret, succeeding when it is absent."""
        backend = self._backend()
        try:
            if backend.get_password(self.service, key) is not None:
                backend.delete_password(self.service, key)
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


def system(service: str) -> Store:
    """Return storage backed by the optional system keyring package."""
    return _System(service)


def memory() -> Store:
    """Return volatile storage intended for tests."""
    return _Memory()


# TODO: Add keyring.file(directory) when a concrete file-backed store is required.
