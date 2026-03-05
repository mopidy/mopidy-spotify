import base64
import json
import secrets
import urllib.parse
import urllib.request
from pathlib import Path


class SpotifyDirectAuthentication:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_url: str,
        credentials: dict[str, str] | None = None,
        cache_credentials_path: str | None = None,
    ):
        self._client_id: str = client_id
        self._client_secret: str = client_secret
        self._refresh_url: str = refresh_url
        self._credentials: dict[str, str] | None = credentials
        self._cache_credentials_path: str | None = cache_credentials_path

    def _save_token(self, token: dict[str, str]) -> None:
        if self._cache_credentials_path:
            with Path(self._cache_credentials_path).open("w") as f:
                json.dump(token, f)

    def _load_token(self) -> dict[str, str] | None:
        if self._cache_credentials_path and Path(self._cache_credentials_path).exists():
            with Path(self._cache_credentials_path).open() as f:
                return json.load(f)
        return None

    def _spotify_token_request(self, payload: dict[str, str]) -> dict[str, str]:
        url = "https://accounts.spotify.com/api/token"
        # Validate URL scheme is https
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme != "https":
            msg = f"Invalid URL scheme: {parsed_url.scheme}"
            raise RuntimeError(msg)

        auth_str = f"{self._client_id}:{self._client_secret}"
        auth_header = base64.b64encode(auth_str.encode()).decode()

        encoded_data = urllib.parse.urlencode(payload).encode()

        req = urllib.request.Request(url, data=encoded_data, method="POST")  # noqa: S310
        req.add_header("Authorization", f"Basic {auth_header}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req) as response:  # noqa: S310
            return json.loads(response.read().decode())

    def _refresh_access_token(self, refresh_token: str) -> dict[str, str]:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        new_token = self._spotify_token_request(data)
        if "refresh_token" not in new_token:
            new_token["refresh_token"] = refresh_token
        return new_token

    def _exchange_code_for_token(self, code: str) -> dict[str, str]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._refresh_url,
        }
        return self._spotify_token_request(data)

    def _authenticate(self) -> dict[str, str]:
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

    def fetch_token(self) -> dict[str, str]:
        token = self._credentials or self._load_token()

        if not token:
            token = self._authenticate()
        else:
            token = self._refresh_access_token(token["refresh_token"])

        self._save_token(token)
        return token
