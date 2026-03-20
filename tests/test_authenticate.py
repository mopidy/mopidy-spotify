import builtins
import json
import secrets

import pytest

from mopidy_spotify.authenticate import SpotifyDirectAuthentication

mock_secret = secrets.token_urlsafe(16)
mock_old_token = secrets.token_urlsafe(16)
mock_new_token = secrets.token_urlsafe(16)


def test_fetch_from_disk_token_refreshes_and_caches(tmp_path, monkeypatch):
    cache_path = tmp_path / "token.json"
    cache_path.write_text(json.dumps({"refresh_token": mock_old_token}))

    auth = SpotifyDirectAuthentication(
        client_id="id",
        client_secret=mock_secret,
        refresh_url="https://example.com/redirect",
        cache_credentials_path=str(cache_path),
    )

    def fake_token_request(self, payload: dict[str, str]) -> tuple[dict[str, str], int]:
        assert payload["grant_type"] == "refresh_token"
        assert payload["refresh_token"] == mock_old_token
        return {"access_token": mock_new_token}, 200

    monkeypatch.setattr(
        SpotifyDirectAuthentication, "_spotify_token_request", fake_token_request
    )

    token, status_code = auth.fetch_token()

    assert token is not None
    assert token["access_token"] == mock_new_token
    assert token["refresh_token"] == mock_old_token
    assert status_code == 200

    assert json.loads(cache_path.read_text()) == token

def test_fetch_from_memory_token_refreshes_and_caches(tmp_path, monkeypatch):
    auth = SpotifyDirectAuthentication(
        client_id="id",
        client_secret=mock_secret,
        refresh_url="https://example.com/redirect",
    )
    auth._credentials = {"refresh_token": mock_old_token}

    def fake_token_request(self, payload: dict[str, str]) -> tuple[dict[str, str], int]:
        assert payload["grant_type"] == "refresh_token"
        assert payload["refresh_token"] == mock_old_token
        return {"access_token": mock_new_token}, 200

    monkeypatch.setattr(
        SpotifyDirectAuthentication, "_spotify_token_request", fake_token_request
    )

    token, status_code = auth.fetch_token()

    assert token is not None
    assert token["access_token"] == mock_new_token
    assert token["refresh_token"] == mock_old_token
    assert status_code == 200

def test_authenticate_flow_saves_token(tmp_path, monkeypatch):
    cache_path = tmp_path / "token.json"

    # Ensure the state is predictable.
    monkeypatch.setattr(
        "mopidy_spotify.authenticate.secrets.token_urlsafe", lambda n: "fixedstate"
    )

    # Simulate browser redirect with expected state and code.
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "https://example.com/callback?code=code123&state=fixedstate",
    )

    def fake_token_request(self, payload: dict[str, str]) -> tuple[dict[str, str], int]:
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "code123"
        return {"access_token": "tok", "refresh_token": "rtok"}, 200

    monkeypatch.setattr(
        SpotifyDirectAuthentication, "_spotify_token_request", fake_token_request
    )

    auth = SpotifyDirectAuthentication(
        client_id="id",
        client_secret=mock_secret,
        refresh_url="https://example.com/redirect",
        cache_credentials_path=str(cache_path),
    )

    token, status_code = auth.fetch_token()

    assert status_code == 200
    assert token == {"access_token": "tok", "refresh_token": "rtok"}
    assert json.loads(cache_path.read_text()) == token


def test_authenticate_state_mismatch_raises(monkeypatch):
    monkeypatch.setattr(
        "mopidy_spotify.authenticate.secrets.token_urlsafe", lambda n: "expected"
    )
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "https://example.com/callback?code=code123&state=wrong",
    )

    auth = SpotifyDirectAuthentication(
        client_id="id",
        client_secret=mock_secret,
        refresh_url="https://example.com/redirect",
    )

    with pytest.raises(RuntimeError, match="STATE MISMATCH"):
        auth.fetch_token()


def test_authenticate_missing_code_raises(monkeypatch):
    monkeypatch.setattr(
        "mopidy_spotify.authenticate.secrets.token_urlsafe", lambda n: "expected"
    )
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt="": "https://example.com/callback?state=expected",
    )

    auth = SpotifyDirectAuthentication(
        client_id="id",
        client_secret=mock_secret,
        refresh_url="https://example.com/redirect",
    )

    with pytest.raises(RuntimeError, match="Authorization failed"):
        auth.fetch_token()
