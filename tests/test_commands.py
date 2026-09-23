import json
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from mopidy.config import Config

from mopidy_spotify import Extension, commands
from mopidy_spotify.commands import logout, run_auth_command
from mopidy_spotify.oauth import pkce, state
from mopidy_spotify.oauth.flow import (
    AuthChallenge,
    AuthExchangeError,
    AuthFlow,
    AuthFlowError,
    AuthInvalidStateError,
    TokenExchangeResponse,
)

type FinishCallback = Callable[[AuthChallenge, str], None]


class StubAuthFlow:
    def __init__(
        self,
        *,
        challenge: AuthChallenge | None = None,
        finish_error: AuthFlowError | None = None,
        finish_callback: FinishCallback | None = None,
    ) -> None:
        self.challenge = challenge or AuthChallenge(
            "https://accounts.spotify.com/authorize?foo=bar",
            "state-123",
            "verifier-123",
        )
        self.finish_error = finish_error
        self.finish_callback = finish_callback

    def start_auth(self) -> AuthChallenge:
        return self.challenge

    def finish_auth(self, challenge: AuthChallenge, pasted_result: str):
        if self.finish_callback is not None:
            self.finish_callback(challenge, pasted_result)
        if self.finish_error is not None:
            raise self.finish_error


def test_logout_command(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    with mock.patch.object(Config, "get_global", return_value=config):
        credentials_dir = Extension().get_credentials_dir(config)
        auth_state_path = Extension.get_auth_state_path(config)
        (credentials_dir / "foo").mkdir()
        (credentials_dir / "bar").touch()
        auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        auth_state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mode": "pkce",
                    "state": "authorized",
                    "refresh_token": "refresh-token-123",
                }
            ),
            encoding="utf-8",
        )

        logout()

        assert not credentials_dir.is_dir()
        assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
            "version": 1,
            "mode": "pkce",
            "state": "cleared",
        }


def test_logout_command_handles_corrupt_auth_state(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    with mock.patch.object(Config, "get_global", return_value=config):
        credentials_dir = Extension().get_credentials_dir(config)
        auth_state_path = Extension.get_auth_state_path(config)
        (credentials_dir / "foo").mkdir()
        (credentials_dir / "bar").touch()
        auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        auth_state_path.write_text("not-json", encoding="utf-8")

        logout()

        assert not credentials_dir.is_dir()
        assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
            "version": 1,
            "mode": "bridge",
            "state": "cleared",
        }


def test_logout_clears_auth_state_when_credentials_cleanup_fails(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    credentials_dir = Extension.get_credentials_dir(config)
    auth_state_path = Extension.get_auth_state_path(config)
    auth_state_path.parent.mkdir(parents=True, exist_ok=True)
    state.FileAuthStateStore(auth_state_path).save(
        state.PkceAuthorizedAuthPayload(
            refresh_token="refresh-token-123"  # noqa: S106
        )
    )

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(Path, "rmdir", side_effect=PermissionError),
    ):
        logout()

    assert credentials_dir.exists()
    assert state.FileAuthStateStore(auth_state_path).load() == (
        state.ClearedAuthPayload(mode="pkce")
    )


def test_logout_clears_credentials_when_auth_state_cleanup_fails(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    credentials_dir = Extension.get_credentials_dir(config)
    auth_state_path = Extension.get_auth_state_path(config)

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            state.FileAuthStateStore,
            "save",
            side_effect=PermissionError,
        ),
    ):
        logout()

    assert not credentials_dir.exists()
    assert not auth_state_path.exists()


def test_auth_command_stores_refresh_token(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    auth_state_path = Extension.get_auth_state_path(
        Config({"core": {"data_dir": tmp_path}})
    )

    flow = AuthFlow(
        Config({"proxy": {}}),
        auth_state_path,
        generate_pkce_verifier=lambda: ("verifier-123", "challenge-123"),
        generate_state=lambda: "state-123",
        generate_authorization_url=lambda challenge, state: (
            f"https://accounts.spotify.com/authorize?challenge={challenge}&state={state}"
        ),
        parse_authorization_result=lambda result: pkce.AuthorizationResult(
            code="code-123",
            state="state-123",
        ),
        exchange_authorization_code=lambda config, code, verifier: (
            TokenExchangeResponse(refresh_token="refresh-token-123")  # noqa: S106
        ),
    )

    run_auth_command(
        flow,
        read_input=lambda: "https://mopidy.com/auth/spotify",
    )

    captured = capsys.readouterr()

    assert "After authorizing, paste the result shown in your browser" in captured.out
    assert (
        "https://accounts.spotify.com/authorize?challenge=challenge-123&state=state-123"
        in captured.out
    )
    assert "Refresh token successfully stored." in captured.out
    assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": "refresh-token-123",
    }
    assert auth_state_path.stat().st_mode & 0o777 == 0o600


def test_auth_command_separates_url_prompt_input_and_success_output():
    output: list[str] = []

    result = run_auth_command(
        StubAuthFlow(),
        read_input=lambda: "https://mopidy.com/auth/spotify",
        write_output=lambda value="": output.append(value),
    )

    assert result == 0
    assert output == [
        "Please visit the following URL:\n",
        "https://accounts.spotify.com/authorize?foo=bar",
        "",
        "After authorizing, paste the result shown in your browser here:\n",
        "",
        "",
        "Refresh token successfully stored.",
    ]


def test_auth_command_replaces_existing_refresh_token(
    tmp_path: Path,
):
    auth_state_path = Extension.get_auth_state_path(
        Config({"core": {"data_dir": tmp_path}})
    )

    flow = StubAuthFlow(
        finish_callback=lambda challenge, pasted_result: (
            auth_state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "mode": "pkce",
                        "state": "authorized",
                        "refresh_token": "refresh-token-456",
                    }
                ),
                encoding="utf-8",
            ),
        )[-1],
    )

    auth_state_path.parent.mkdir(parents=True, exist_ok=True)
    auth_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "pkce",
                "state": "authorized",
                "refresh_token": "refresh-token-123",
            }
        ),
        encoding="utf-8",
    )

    run_auth_command(flow, read_input=lambda: "https://mopidy.com/auth/spotify")

    assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": "refresh-token-456",
    }


def test_auth_command_reports_auth_errors(capsys: pytest.CaptureFixture[str]):
    flow = StubAuthFlow(finish_error=AuthExchangeError("access_denied"))

    result = run_auth_command(
        flow, read_input=lambda: "https://mopidy.com/auth/spotify"
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Something went wrong: access_denied" in captured.out


def test_auth_command_reports_invalid_state(capsys: pytest.CaptureFixture[str]):
    flow = StubAuthFlow(finish_error=AuthInvalidStateError())

    result = run_auth_command(
        flow, read_input=lambda: "https://mopidy.com/auth/spotify"
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Incorrect state returned, please try again." in captured.out


def test_auth_command_handles_aborted_input(capsys: pytest.CaptureFixture[str]):
    flow = StubAuthFlow()

    result = run_auth_command(flow, read_input=lambda: (_ for _ in ()).throw(EOFError))

    captured = capsys.readouterr()
    assert result == 1
    assert "Authentication aborted." in captured.out


def test_auth_command_uses_global_config_and_extension_state_path(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    flow = mock.Mock(spec=AuthFlow)

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(commands.flow, "AuthFlow", return_value=flow) as create,
        mock.patch.object(commands, "run_auth_command", return_value=7) as run,
    ):
        result = commands.auth()

    assert result == 7
    create.assert_called_once_with(config, Extension.get_auth_state_path(config))
    run.assert_called_once_with(flow)
