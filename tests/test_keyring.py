from unittest import mock

import pytest

from mopidy_spotify._ext import keyring


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[service, username]


@pytest.fixture(params=["memory", "system"])
def store(request: pytest.FixtureRequest):
    if request.param == "memory":
        yield keyring.memory()
        return
    with mock.patch.object(
        keyring.importlib,
        "import_module",
        return_value=MemoryBackend(),
    ):
        yield keyring.system("example-extension")


def test_store_contract(store: keyring.Store):
    assert store.load("secret-id") is None

    store.save("secret-id", "first-secret")
    assert store.load("secret-id") == "first-secret"

    store.save("secret-id", "second-secret")
    assert store.load("secret-id") == "second-secret"

    store.clear("secret-id")
    assert store.load("secret-id") is None
    store.clear("secret-id")


@pytest.mark.parametrize("operation", ["load", "save", "clear"])
def test_system_store_wraps_backend_errors(operation: str):
    backend = mock.Mock()
    store = keyring.system("service")
    method_name = {
        "load": "get_password",
        "save": "set_password",
        "clear": "get_password",
    }[operation]
    getattr(backend, method_name).side_effect = RuntimeError("backend failed")

    with (
        mock.patch.object(keyring.importlib, "import_module", return_value=backend),
        pytest.raises(keyring.Error),
    ):
        getattr(store, operation)(
            "username",
            *("secret",) if operation == "save" else (),
        )


def test_system_store_reports_unavailable_backend_when_loading():
    store = keyring.system("service")

    with (
        mock.patch.object(keyring.importlib, "import_module", side_effect=ImportError),
        pytest.raises(keyring.UnavailableError, match="unavailable"),
    ):
        store.load("username")


def test_system_store_reports_unavailable_backend_when_saving():
    store = keyring.system("service")

    with (
        mock.patch.object(keyring.importlib, "import_module", side_effect=ImportError),
        pytest.raises(keyring.UnavailableError, match="unavailable"),
    ):
        store.save("username", "secret")


def test_system_store_reports_unavailable_backend_when_clearing():
    store = keyring.system("service")

    with (
        mock.patch.object(keyring.importlib, "import_module", side_effect=ImportError),
        pytest.raises(keyring.UnavailableError, match="unavailable"),
    ):
        store.clear("username")
