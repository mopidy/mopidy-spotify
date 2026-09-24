import json
from pathlib import Path
from unittest import mock

import pytest
import requests
from mopidy.config import Config

from mopidy_spotify.oauth import manifest, pkce
from mopidy_spotify.oauth.flow import (
    AuthChallenge,
    AuthExchangeError,
    AuthFlow,
    AuthMissingCodeError,
    AuthStateMismatchError,
    TokenExchangeResponse,
    _exchange_authorization_code,
)


def exchange_response(**payload: object):
    return TokenExchangeResponse.model_validate(payload)


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
        Path("auth.json"),
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


def test_finish_auth_persists_refresh_token_on_success(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    token_value = "token-123"  # noqa: S105
    challenge = AuthChallenge("https://example.com", "state-123", "verifier-123")
    flow = AuthFlow(
        Config({"proxy": {}}),
        auth_state_path,
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
    assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {"storage": "inline", "value": token_value},
    }


def test_finish_auth_reports_unavailable_selected_keyring(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
        storage_type=manifest.StorageType.KEYRING,
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            state="state-123",
            code="code-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: exchange_response(
            refresh_token="refresh-token"  # noqa: S106
        ),
    )

    with (
        mock.patch.dict("sys.modules", {"keyring": None}),
        pytest.raises(AuthExchangeError, match="Keyring backend is unavailable"),
    ):
        flow.finish_auth(
            AuthChallenge("https://example.com", "state-123", "verifier-123"),
            "ignored",
        )


def test_finish_auth_rejects_invalid_state(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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


def test_finish_auth_rejects_missing_code(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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


def test_finish_auth_reports_exchange_failure(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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


def test_finish_auth_reports_provider_error(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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


def test_finish_auth_rejects_success_without_refresh_token(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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


def test_finish_auth_reports_malformed_authorization_result(tmp_path: Path):
    flow = AuthFlow(
        Config({"proxy": {}}),
        tmp_path / "auth.json",
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
