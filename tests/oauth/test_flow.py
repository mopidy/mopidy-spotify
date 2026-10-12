import json
from pathlib import Path
from typing import cast
from unittest import mock

import pytest
import requests
from mopidy.config import Config
from pydantic import SecretStr

from mopidy_spotify._ext import atomic, keyring
from mopidy_spotify.oauth import pkce, state, store
from mopidy_spotify.oauth.flow import (
    AuthChallenge,
    AuthExchangeError,
    AuthFlow,
    AuthMissingCodeError,
    AuthStateMismatchError,
    StoragePolicy,
    TokenExchangeResponse,
    _exchange_authorization_code,
    authorization_writer,
)


def exchange_response(**payload: object):
    return TokenExchangeResponse.model_validate(payload)


def initial_flow(path: Path, policy: StoragePolicy = StoragePolicy.AUTO) -> AuthFlow:
    return AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=authorization_writer(store.Store(path), policy),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123", code="code-123"
        ),
        exchange_authorization_code=lambda config, code, verifier: (
            TokenExchangeResponse(refresh_token=SecretStr("refresh-token"))
        ),
    )


def raise_invalid_authorization_response(result: str):
    _ = result
    message = "invalid authorization response."
    raise ValueError(message)


@pytest.mark.parametrize(("configured", "expected"), [(7, 7), (0, 1)])
def test_exchange_authorization_code_uses_configured_timeout(
    configured: int,
    expected: int,
):
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"refresh_token":"token-123"}'

    with mock.patch.object(
        requests.Session,
        "send",
        return_value=response,
    ) as send:
        result = _exchange_authorization_code(
            Config({"proxy": {}, "spotify": {"timeout": configured}}),
            "code-123",
            "verifier-123",
        )

    request = send.call_args.args[0]
    assert request.url == "https://accounts.spotify.com/api/token"
    assert request.body == (
        "client_id=f88ee52f92724d51b7579a1d1cdb3128&"
        "grant_type=authorization_code&code=code-123&"
        "redirect_uri=https%3A%2F%2Fmopidy.com%2Fauth%2Fspotify&"
        "code_verifier=verifier-123"
    )
    assert send.call_args.kwargs["timeout"] == expected
    assert result == TokenExchangeResponse(refresh_token="token-123")  # noqa: S106
    assert "token-123" not in repr(result)


def test_exchange_authorization_code_sanitizes_validation_error(
    caplog: pytest.LogCaptureFixture,
):
    refresh_token = "refresh-token-must-not-leak"  # noqa: S105
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {
            "refresh_token": refresh_token,
            "error_description": 1,
        }
    ).encode()
    caplog.set_level("DEBUG", logger="mopidy_spotify.oauth.flow")

    with (
        mock.patch.object(requests.Session, "send", return_value=response),
        pytest.raises(ValueError, match="invalid token response") as exc_info,
    ):
        _exchange_authorization_code(
            Config({"proxy": {}, "spotify": {"timeout": 10}}),
            "code-123",
            "verifier-123",
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert refresh_token not in caplog.text
    assert "string_type" in caplog.text


def test_exchange_authorization_code_reports_network_failure():
    with (
        mock.patch.object(
            requests.Session,
            "send",
            side_effect=requests.ConnectionError("Spotify is unreachable"),
        ),
        pytest.raises(ValueError, match="Spotify is unreachable") as exc_info,
    ):
        _exchange_authorization_code(
            Config({"proxy": {}, "spotify": {"timeout": 10}}),
            "code-123",
            "verifier-123",
        )

    assert isinstance(exc_info.value.__cause__, requests.ConnectionError)


def test_exchange_authorization_code_reports_invalid_json():
    response = requests.Response()
    response.status_code = 200
    response._content = b"not-json"

    with (
        mock.patch.object(requests.Session, "send", return_value=response),
        pytest.raises(ValueError, match="invalid token response") as exc_info,
    ):
        _exchange_authorization_code(
            Config({"proxy": {}, "spotify": {"timeout": 10}}),
            "code-123",
            "verifier-123",
        )

    assert isinstance(exc_info.value.__cause__, requests.JSONDecodeError)


def test_exchange_authorization_code_requires_token_or_error():
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"

    with (
        mock.patch.object(requests.Session, "send", return_value=response),
        pytest.raises(ValueError, match="missing refresh_token"),
    ):
        _exchange_authorization_code(
            Config({"proxy": {}, "spotify": {"timeout": 10}}),
            "code-123",
            "verifier-123",
        )


def test_start_auth_returns_typed_challenge():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        generate_pkce_verifier=lambda: ("verifier-123", "challenge-123"),
        generate_state=lambda: "state-123",
        generate_authorization_url=lambda challenge, state: (
            f"https://example.com/{challenge}/{state}"
        ),
    )
    challenge = flow.start_auth()

    assert challenge == AuthChallenge(
        authorization_url="https://example.com/challenge-123/state-123",
        state="state-123",
        verifier="verifier-123",
    )


def test_finish_auth_passes_refresh_token_to_injected_writer():
    persist = mock.Mock()
    token_value = "token-123"  # noqa: S105
    challenge = AuthChallenge("https://example.com", "state-123", "verifier-123")
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=persist,
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="code-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: exchange_response(
            refresh_token=token_value
        ),
    )

    result = flow.finish_auth(
        challenge,
        "ignored",
    )

    assert result is None
    persist.assert_called_once_with(SecretStr(token_value))


def test_finish_auth_propagates_writer_failure():
    error = AuthExchangeError("storage unavailable")
    persist = mock.Mock(side_effect=error)
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=persist,
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123", code="code-123"
        ),
        exchange_authorization_code=lambda config, code, verifier: (
            TokenExchangeResponse(refresh_token=SecretStr("refresh-token"))
        ),
    )

    with pytest.raises(AuthExchangeError) as exc:
        flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")

    assert exc.value is error
    persist.assert_called_once_with(SecretStr("refresh-token"))


def test_finish_auth_rejects_invalid_state():
    persist = mock.Mock()
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=persist,
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="wrong-state",
            code="code-123",
        ),
    )

    with pytest.raises(AuthStateMismatchError):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )
    persist.assert_not_called()


def test_finish_auth_rejects_missing_code():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="",
        ),
    )

    with pytest.raises(AuthMissingCodeError):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


def test_finish_auth_reports_exchange_failure():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="code-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: (
            _ for _ in ()
        ).throw(ValueError("network down")),
    )

    with pytest.raises(AuthExchangeError, match="Something went wrong: network down"):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


def test_finish_auth_reports_provider_error():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="code-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: exchange_response(
            error="access_denied"
        ),
    )

    with pytest.raises(AuthExchangeError, match="Something went wrong: access_denied"):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


def test_finish_auth_rejects_success_without_refresh_token():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="code-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: (
            TokenExchangeResponse()
        ),
    )

    with pytest.raises(AuthExchangeError, match="missing refresh_token"):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


def test_finish_auth_reports_malformed_authorization_result():
    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=mock.Mock(),
        parse_authorization_result=raise_invalid_authorization_response,
    )

    with pytest.raises(
        AuthExchangeError,
        match=r"Something went wrong: invalid authorization response\.",
    ):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


@pytest.mark.parametrize("policy", list(StoragePolicy))
def test_building_writer_does_not_access_keyring(tmp_path: Path, policy: StoragePolicy):
    with mock.patch.object(keyring, "system") as create:
        authorization_writer(store.Store(tmp_path / "auth.json"), policy)

    create.assert_not_called()


def test_selected_keyring_reports_unavailable_backend(tmp_path: Path):
    auth_flow = initial_flow(tmp_path / "auth.json", StoragePolicy.KEYRING)
    with (
        mock.patch.dict("sys.modules", {"keyring": None}),
        pytest.raises(AuthExchangeError, match="keyring is unavailable"),
    ):
        auth_flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")


def test_auto_stores_actual_token_in_keyring_without_probe(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "auth.json"
    backend = mock.Mock(spec=keyring.Store, wraps=keyring.memory())
    auth_flow = initial_flow(path)

    with mock.patch.object(keyring, "system", return_value=backend):
        auth_flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")

    assert backend.save.call_count == 1
    backend.load.assert_not_called()
    backend.clear.assert_not_called()
    username, value = backend.save.call_args.args
    assert value == "refresh-token"
    assert backend.load(username) == value
    saved = json.loads(path.read_text())
    assert saved["refresh_token"]["storage"] == "keyring"
    assert saved["refresh_token"]["username"] == username
    assert "stored in plaintext" not in caplog.text


def test_auto_warns_and_stores_plaintext_when_keyring_is_not_installed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "auth.json"
    auth_flow = initial_flow(path)

    with mock.patch.dict("sys.modules", {"keyring": None}):
        auth_flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")

    assert json.loads(path.read_text())["refresh_token"] == {
        "storage": "inline",
        "value": "refresh-token",
    }
    assert "stored in plaintext" in caplog.text
    assert "--storage keyring" in caplog.text
    assert "refresh-token" not in caplog.text


@pytest.mark.parametrize("policy", [StoragePolicy.AUTO, StoragePolicy.KEYRING])
def test_fallback_only_in_auto_after_keyring_staging_failure(
    tmp_path: Path,
    policy: StoragePolicy,
    caplog: pytest.LogCaptureFixture,
):
    path = tmp_path / "auth.json"
    auth_store = store.Store(path)
    auth_store.persist_pkce_authorization(SecretStr("previous-token"))
    previous = auth_store.load()
    memory = keyring.memory()
    backend = mock.Mock(spec=keyring.Store, wraps=memory)
    backend.save.side_effect = keyring.Error("locked")
    auth_flow = initial_flow(path, policy)

    with mock.patch.object(keyring, "system", return_value=backend):
        if policy == StoragePolicy.AUTO:
            auth_flow.finish_auth(
                AuthChallenge("url", "state-123", "verifier"), "ignored"
            )
            assert json.loads(path.read_text())["refresh_token"]["storage"] == "inline"
            snapshot = auth_store.load()
            assert snapshot is not None
            assert snapshot.state == state.PkceAuthorized(
                refresh_token=SecretStr("refresh-token")
            )
            assert "stored in plaintext" in caplog.text
        else:
            with pytest.raises(AuthExchangeError, match="Could not save"):
                auth_flow.finish_auth(
                    AuthChallenge("url", "state-123", "verifier"), "ignored"
                )
            assert auth_store.load() == previous
            assert "stored in plaintext" not in caplog.text

    username = backend.save.call_args.args[0]
    assert memory.load(username) is None
    assert "refresh-token" not in caplog.text


@pytest.mark.parametrize("failure", ["write", "sync"])
def test_auto_does_not_fall_back_after_manifest_persistence_failure(
    tmp_path: Path, failure: str, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "auth.json"
    auth_store = store.Store(path)
    auth_store.persist_pkce_authorization(SecretStr("previous-token"))
    previous = auth_store.load()
    memory = keyring.memory()
    auth_flow = initial_flow(path)
    operation = "write" if failure == "write" else "_sync_directory"

    with (
        mock.patch.object(keyring, "system", return_value=memory),
        mock.patch.object(
            atomic, operation, side_effect=OSError("disk failure")
        ) as write,
        pytest.raises(AuthExchangeError, match="Could not save"),
    ):
        auth_flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")

    assert write.call_count == 1
    if failure == "write":
        assert auth_store.load() == previous
    else:
        saved = json.loads(path.read_text())["refresh_token"]
        assert saved["storage"] == "keyring"
        assert memory.load(saved["username"]) == "refresh-token"
    assert "stored in plaintext" not in caplog.text


def test_plaintext_setup_does_not_attempt_keyring(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "auth.json"
    auth_flow = initial_flow(path, StoragePolicy.PLAINTEXT)
    with mock.patch.object(keyring, "system", side_effect=AssertionError) as create:
        auth_flow.finish_auth(AuthChallenge("url", "state-123", "verifier"), "ignored")

    create.assert_not_called()
    assert json.loads(path.read_text())["refresh_token"]["storage"] == "inline"
    assert "stored in plaintext" not in caplog.text


def test_auto_propagates_plaintext_failure_after_keyring_failure(tmp_path: Path):
    auth_store = store.Store(tmp_path / "auth.json")
    auth_store.persist_pkce_authorization(SecretStr("previous-token"))
    previous = auth_store.load()
    writer = authorization_writer(auth_store, StoragePolicy.AUTO)

    with (
        mock.patch.dict("sys.modules", {"keyring": None}),
        mock.patch.object(
            atomic, "write", side_effect=OSError("disk failure")
        ) as write,
        pytest.raises(AuthExchangeError, match="authorization state"),
    ):
        writer(SecretStr("refresh-token"))

    assert write.call_count == 1
    assert auth_store.load() == previous


def test_writer_rejects_unsupported_policy_without_changing_authorization(
    tmp_path: Path,
):
    auth_store = store.Store(tmp_path / "auth.json")
    auth_store.persist_pkce_authorization(SecretStr("previous-token"))
    previous = auth_store.load()
    writer = authorization_writer(auth_store, cast("StoragePolicy", "unsupported"))

    with pytest.raises(AssertionError):
        writer(SecretStr("refresh-token"))

    assert auth_store.load() == previous
