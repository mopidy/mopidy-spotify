import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from mopidy.config import Config
from pydantic import SecretStr

from mopidy_spotify import Extension, commands
from mopidy_spotify._ext import keyring
from mopidy_spotify.commands import logout, run_auth_command
from mopidy_spotify.oauth import manifest, pkce, providers, state, store, tokens
from mopidy_spotify.oauth.flow import (
    AuthChallenge,
    AuthExchangeError,
    AuthFlow,
    AuthFlowError,
    AuthStateMismatchError,
    StoragePolicy,
    TokenExchangeResponse,
    authorization_writer,
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
                    "refresh_token": {
                        "storage": "inline",
                        "value": "refresh-token-123",
                    },
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
    store.Store(auth_state_path).persist_pkce_authorization(
        SecretStr("refresh-token-123")
    )

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(Path, "rmdir", side_effect=PermissionError),
    ):
        logout()

    assert credentials_dir.exists()
    snapshot = store.Store(auth_state_path).load()
    assert snapshot is not None
    assert snapshot.state == state.Cleared(mode="pkce")


def test_logout_clears_credentials_when_auth_state_cleanup_fails(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    credentials_dir = Extension.get_credentials_dir(config)
    auth_state_path = Extension.get_auth_state_path(config)

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            store.Store,
            "clear",
            side_effect=PermissionError,
        ),
    ):
        logout()

    assert not credentials_dir.exists()
    assert not auth_state_path.exists()


def test_logout_clears_web_authorization_when_playback_path_is_blocked(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.persist_pkce_authorization(SecretStr("refresh-token"))
    (Extension.get_data_dir(config) / "credentials-cache").write_text("blocked")

    with mock.patch.object(Config, "get_global", return_value=config):
        logout()

    snapshot = auth_store.load()
    assert snapshot is not None
    assert snapshot.state == state.Cleared(mode="pkce")


def test_auth_command_stores_refresh_token(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    auth_state_path = Extension.get_auth_state_path(
        Config({"core": {"data_dir": tmp_path}})
    )

    flow = AuthFlow(
        Config({"proxy": {}}),
        persist_authorization=authorization_writer(
            store.Store(auth_state_path), StoragePolicy.PLAINTEXT
        ),
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
        "refresh_token": {
            "storage": "inline",
            "value": "refresh-token-123",
        },
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
                        "refresh_token": {
                            "storage": "inline",
                            "value": "refresh-token-456",
                        },
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
                "refresh_token": {
                    "storage": "inline",
                    "value": "refresh-token-123",
                },
            }
        ),
        encoding="utf-8",
    )

    run_auth_command(flow, read_input=lambda: "https://mopidy.com/auth/spotify")

    assert json.loads(auth_state_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "mode": "pkce",
        "state": "authorized",
        "refresh_token": {
            "storage": "inline",
            "value": "refresh-token-456",
        },
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
    flow = StubAuthFlow(finish_error=AuthStateMismatchError())

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


def test_web_auth_command_uses_global_config_and_extension_state_path(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    flow = mock.Mock(spec=AuthFlow)
    writer = mock.Mock()

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            commands.flow, "authorization_writer", return_value=writer
        ) as compose,
        mock.patch.object(commands.flow, "AuthFlow", return_value=flow) as create,
        mock.patch.object(commands, "run_auth_command", return_value=7) as run,
    ):
        result = commands.web()

    assert result == 7
    create.assert_called_once_with(config, persist_authorization=writer)
    assert compose.call_count == 1
    auth_store, policy = compose.call_args.args
    assert auth_store.path == Extension.get_auth_state_path(config)
    assert policy == StoragePolicy.AUTO
    run.assert_called_once_with(flow)


def test_bare_auth_is_reserved_for_help():
    assert commands.auth_app.default_command is None


def test_legacy_flag_switches_from_pkce_without_clearing_playback(tmp_path: Path):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "bridge-id", "client_secret": "bridge-secret"},
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.persist_pkce_authorization(SecretStr("refresh-token"))
    previous = auth_store.load()
    credentials = Extension.get_credentials_dir(config) / "credentials.json"
    credentials.write_text("playback-credentials")

    with mock.patch.object(Config, "get_global", return_value=config):
        with pytest.raises(SystemExit) as result:
            commands.app(["auth", "web", "--legacy"])
        assert result.value.code == 0

    snapshot = auth_store.load()
    assert snapshot is not None
    assert snapshot.state == state.BridgeConfigured()
    assert json.loads(auth_store.path.read_text()) == {
        "version": 1,
        "mode": "bridge",
        "state": "configured",
    }
    provider = providers.BridgeProvider("bridge-id", "bridge-secret")
    assert provider.supports(snapshot.state)
    assert not providers.PkceProvider().supports(snapshot.state)
    assert not auth_store.compare_and_set(
        previous, state.PkceAuthorized(refresh_token=SecretStr("stale-token"))
    )
    assert credentials.read_text() == "playback-credentials"


@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [(None, None), ("bridge-id", None), (None, "bridge-secret"), ("", "bridge-secret")],
)
def test_legacy_flag_persists_intent_without_complete_credentials(
    tmp_path: Path,
    client_id: str | None,
    client_secret: str | None,
    caplog: pytest.LogCaptureFixture,
):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": client_id, "client_secret": client_secret},
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.persist_pkce_authorization(SecretStr("refresh-token"))
    with mock.patch.object(Config, "get_global", return_value=config):
        assert commands.web(legacy=True) == 0

    snapshot = auth_store.load()
    assert snapshot is not None
    assert snapshot.state == state.BridgeConfigured()
    assert "Configure both" in caplog.text


def test_legacy_flag_preserves_saved_rejection(tmp_path: Path):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "bridge-id", "client_secret": "bridge-secret"},
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    provider = providers.BridgeProvider("bridge-id", "bridge-secret")
    rejection = provider.process(
        None, tokens.OAuthErrorResponse(error="invalid_grant"), 400
    )
    assert auth_store.compare_and_set(None, rejection)
    assert not provider.supports(rejection)

    with mock.patch.object(Config, "get_global", return_value=config):
        assert commands.web(legacy=True) == 0

    snapshot = auth_store.load()
    assert snapshot is not None
    assert snapshot.state == rejection
    assert not provider.supports(snapshot.state)


def test_legacy_flag_retires_keyring_token(tmp_path: Path):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "bridge-id", "client_secret": "bridge-secret"},
        }
    )
    memory_keyring = keyring.memory()
    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(keyring, "system", return_value=memory_keyring),
    ):
        auth_store = store.Store(
            Extension.get_auth_state_path(config),
            generate_keyring_username=lambda: "token-id",
        )
        auth_store.persist_pkce_authorization(
            SecretStr("refresh-token"), manifest.StorageType.KEYRING
        )
        assert memory_keyring.load("token-id") == "refresh-token"

        assert commands.web(legacy=True) == 0

    assert memory_keyring.load("token-id") is None


def test_legacy_flag_reports_storage_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "bridge-id", "client_secret": "bridge-secret"},
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.persist_pkce_authorization(SecretStr("refresh-token"))
    previous = auth_store.load()

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            store.Store, "configure_bridge", side_effect=store.Error("unavailable")
        ),
    ):
        assert commands.web(legacy=True) == 1

    assert auth_store.load() == previous
    assert "Could not complete the switch" in caplog.text


@pytest.mark.parametrize("policy", list(StoragePolicy))
def test_web_auth_storage_flag_selects_setup_policy(
    tmp_path: Path, policy: StoragePolicy
):
    config = Config({"core": {"data_dir": tmp_path}})
    writer = mock.Mock()
    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            commands.flow, "authorization_writer", return_value=writer
        ) as compose,
        mock.patch.object(commands.flow, "AuthFlow") as create,
        mock.patch.object(commands, "run_auth_command", return_value=0),
    ):
        with pytest.raises(SystemExit) as result:
            commands.app(["auth", "web", "--storage", policy.value])
        assert result.value.code == 0

    create.assert_called_once_with(config, persist_authorization=writer)
    assert compose.call_count == 1
    auth_store, selected = compose.call_args.args
    assert auth_store.path == Extension.get_auth_state_path(config)
    assert selected == policy


def test_legacy_flag_does_not_access_keyring_without_local_authorization(
    tmp_path: Path,
):
    config = Config({"core": {"data_dir": tmp_path}})
    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(keyring, "system") as create,
    ):
        assert commands.web(legacy=True) == 0

    create.assert_not_called()


@pytest.mark.parametrize("storage_choice", ["plaintext", "keyring"])
def test_legacy_flag_rejects_storage_option_without_clearing(
    tmp_path: Path, storage_choice: str
):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "bridge-id", "client_secret": "bridge-secret"},
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.persist_pkce_authorization(SecretStr("previous-token"))
    previous = auth_store.load()
    with mock.patch.object(Config, "get_global", return_value=config):
        with pytest.raises(SystemExit) as result:
            commands.app(["auth", "web", "--legacy", "--storage", storage_choice])
        assert result.value.code == 1

    assert auth_store.load() == previous


@pytest.mark.parametrize("returncode", [0, 1, 7])
def test_playback_auth_runs_gstreamer_helper(tmp_path: Path, returncode: int):
    config = Config({"core": {"data_dir": tmp_path}})
    completed = mock.Mock(returncode=returncode)

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            commands.shutil,
            "which",
            return_value="/usr/bin/gstspotify-auth",
        ),
        mock.patch.object(
            commands.subprocess,
            "run",
            return_value=completed,
        ) as run,
    ):
        result = commands.playback()

    assert result == returncode
    run.assert_called_once_with(
        [
            "/usr/bin/gstspotify-auth",
            os.fspath(Extension.get_data_dir(config) / "credentials-cache"),
        ],
        check=False,
    )


def test_playback_auth_reports_missing_helper(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    config = Config({"core": {"data_dir": tmp_path}})

    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(commands.shutil, "which", return_value=None),
    ):
        result = commands.playback()

    assert result == 1
    assert "Could not find gstspotify-auth" in caplog.text


@pytest.mark.parametrize(
    ("manifest", "bridge", "expected"),
    [
        (None, False, "Spotify Web API: not authorized"),
        (None, True, "Spotify Web API: configured (legacy)"),
        (
            {
                "version": 1,
                "mode": "pkce",
                "state": "authorized",
                "refresh_token": {
                    "storage": "inline",
                    "value": "refresh-token",
                },
            },
            False,
            "Spotify Web API: authorized (PKCE)",
        ),
        (
            {
                "version": 1,
                "mode": "pkce",
                "state": "permanent_error",
                "error_code": "invalid_grant",
            },
            True,
            "Spotify Web API: PKCE authorization rejected",
        ),
    ],
)
def test_auth_status_reports_web_and_playback_separately(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    manifest: dict[str, object] | None,
    *,
    bridge: bool,
    expected: str,
):
    spotify = (
        {"client_id": "client-id", "client_secret": "client-secret"} if bridge else {}
    )
    config = Config({"core": {"data_dir": tmp_path}, "spotify": spotify})
    if manifest is not None:
        auth_path = Extension.get_auth_state_path(config)
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(manifest))
    credentials = Extension.get_credentials_dir(config) / "credentials.json"
    credentials.write_text("playback-credentials")
    with mock.patch.object(Config, "get_global", return_value=config):
        commands.status()

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        expected,
        "Spotify playback: stored",
    ]
    assert captured.err == ""


@pytest.mark.parametrize("changed_credentials", [False, True])
def test_auth_status_distinguishes_rejected_bridge_credentials(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    changed_credentials: bool,
):
    provider = providers.BridgeProvider("client-id", "client-secret")
    rejection = provider.process(
        None, tokens.OAuthErrorResponse(error="invalid_grant"), 400
    )
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {
                "client_id": "client-id",
                "client_secret": "new-secret"
                if changed_credentials
                else "client-secret",
            },
        }
    )
    assert store.Store(Extension.get_auth_state_path(config)).compare_and_set(
        None, rejection
    )

    with mock.patch.object(Config, "get_global", return_value=config):
        commands.status()

    expected = (
        "configured (legacy)"
        if changed_credentials
        else "legacy authorization rejected"
    )
    assert capsys.readouterr().out.splitlines() == [
        f"Spotify Web API: {expected}",
        "Spotify playback: not authorized",
    ]


def test_auth_status_reports_web_when_playback_path_is_blocked(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    config = Config({"core": {"data_dir": tmp_path}})
    store.Store(Extension.get_auth_state_path(config)).persist_pkce_authorization(
        SecretStr("refresh-token")
    )
    (Extension.get_data_dir(config) / "credentials-cache").write_text("blocked")

    with mock.patch.object(Config, "get_global", return_value=config):
        commands.status()

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Spotify Web API: authorized (PKCE)"
    assert lines[1].startswith("Spotify playback: unavailable (")


def test_playback_auth_reports_helper_launch_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
):
    config = Config({"core": {"data_dir": tmp_path}})
    with (
        mock.patch.object(Config, "get_global", return_value=config),
        mock.patch.object(
            commands.shutil, "which", return_value="/usr/bin/gstspotify-auth"
        ),
        mock.patch.object(commands.subprocess, "run", side_effect=PermissionError),
    ):
        assert commands.playback() == 1

    assert "Could not run gstspotify-auth" in caplog.text


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        ("not-json", "invalid authorization state"),
        (
            json.dumps(
                {
                    "version": 1,
                    "mode": "pkce",
                    "state": "authorized",
                    "refresh_token": {
                        "storage": "keyring",
                        "username": "token-id",
                    },
                }
            ),
            "unavailable (Spotify refresh-token keyring is unavailable)",
        ),
    ],
    ids=["corrupt-manifest", "keyring-unavailable"],
)
def test_auth_status_reports_web_failure_without_playback_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contents: str,
    expected: str,
):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {"client_id": "client-id", "client_secret": "client-secret"},
        }
    )
    auth_path = Extension.get_auth_state_path(config)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(contents, encoding="utf-8")
    # Simulate the optional dependency being absent without touching a real keyring.
    monkeypatch.setitem(sys.modules, "keyring", None)

    with mock.patch.object(Config, "get_global", return_value=config):
        commands.status()

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"Spotify Web API: {expected}",
        "Spotify playback: not authorized",
    ]
    assert captured.err == ""
