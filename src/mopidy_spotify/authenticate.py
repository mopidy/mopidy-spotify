import base64
import json
import secrets
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path


class Authentication(ABC):
    @abstractmethod
    def fetch_token(self) -> tuple[dict[str, str] | None, int | None]:
        """Fetch an OAuth token."""


class SpotifyDirectAuthentication(Authentication):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_url: str,
        cache_credentials_path: str | None = None,
    ):
        self._client_id: str = client_id
        self._client_secret: str = client_secret
        self._refresh_url: str = refresh_url
        self._credentials: dict[str, str] | None = None
        self._cache_credentials_path: str | None = cache_credentials_path

    def _save_token(self, token: dict[str, str]) -> None:
        self._credentials = token
        if self._cache_credentials_path:
            with Path(self._cache_credentials_path).open("w") as f:
                json.dump(token, f)

    def _load_token(self) -> dict[str, str] | None:
        if self._cache_credentials_path and Path(self._cache_credentials_path).exists():
            with Path(self._cache_credentials_path).open() as f:
                return json.load(f)
        return None

    def _spotify_token_request(self, payload: dict[str, str]) -> tuple[dict[str, str], int]:
        url = "https://accounts.spotify.com/api/token"

        auth_str = f"{self._client_id}:{self._client_secret}"
        auth_header = base64.b64encode(auth_str.encode()).decode()

        encoded_data = urllib.parse.urlencode(payload).encode()

        req = urllib.request.Request(url, data=encoded_data, method="POST")
        req.add_header("Authorization", f"Basic {auth_header}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode()), response.status

    def _refresh_access_token(self, refresh_token: str) -> tuple[dict[str, str], int]:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        new_token, status = self._spotify_token_request(data)
        if "refresh_token" not in new_token:
            new_token["refresh_token"] = refresh_token
        return new_token, status

    def _exchange_code_for_token(self, code: str) -> tuple[dict[str, str], int]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._refresh_url,
        }
        return self._spotify_token_request(data)

    def _authenticate(self) -> tuple[dict[str, str], int]:
        state = secrets.token_urlsafe(16)

        auth_params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._refresh_url,
            "scope": "playlist-read-private streaming",
            "state": state,
        }
        authorization_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(auth_params)}"
        response_url = input(f"""
Please go here and authorize: {authorization_url}
    Paste the full redirect URL here:
                             """)

        parsed_url = urllib.parse.urlparse(response_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        returned_state = query_params.get("state", [None])[0]
        code = query_params.get("code", [None])[0]

        if returned_state != state:
            msg = "STATE MISMATCH: Possible CSRF attack detected."
            raise RuntimeError(msg)

        if not code:
            msg = "Authorization failed: No code returned."
            raise RuntimeError(msg)

        return self._exchange_code_for_token(code)

    def fetch_token(self) -> tuple[dict[str, str] | None, int | None]:
        token = self._credentials or self._load_token()
        status = None

        if not token:
            token, status = self._authenticate()
        else:
            token, status = self._refresh_access_token(token["refresh_token"])

        self._save_token(token)
        return token, status


class MopidyProxyAuthentication(Authentication):
    def __init__(
        self,
        request,
        auth: tuple[str, str] | None,
        refresh_url: str,
    ):
        self._request = request
        self._auth: tuple[str, str] | None = auth
        self._refresh_url: str = refresh_url

    def _request_with_retries(self, method, url, *args, **kwargs) -> tuple[dict[str, str] | None, int | None]:
        result, status = self._request.execute(method, url, *args, **kwargs)
        return result, status

    def fetch_token(self) -> tuple[dict[str, str] | None, int | None]:
        data = {"grant_type": "client_credentials"}
        return self._request_with_retries(
            "POST", self._refresh_url, auth=self._auth, data=data
        )
