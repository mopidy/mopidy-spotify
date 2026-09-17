from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass

import requests

CLIENT_ID = "f88ee52f92724d51b7579a1d1cdb3128"
REDIRECT_URI = "https://mopidy.com/auth/spotify"
SCOPES = (
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-follow-read",
    "user-library-read",
    "user-library-modify",
    "user-read-recently-played",
    "user-read-private",
    "user-top-read",
    "streaming",
)


@dataclass(frozen=True)
class AuthorizationResult:
    code: str
    state: str


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce_verifier() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_authorization_url(challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": " ".join(SCOPES),
        }
    )
    return f"https://accounts.spotify.com/authorize?{query}"


def parse_authorization_result(result: str) -> AuthorizationResult:
    result = result.strip()
    for parser in (
        _parse_authorization_url,
        _parse_base64_query_string,
    ):
        if parsed_result := parser(result):
            error = parsed_result.get("error")
            if error is not None:
                error_description = parsed_result.get("error_description")
                if error_description is None:
                    raise ValueError(error)

                msg = f"{error}: {error_description}"
                raise ValueError(msg)

            code = parsed_result.get("code")
            state = parsed_result.get("state")
            if code is None or state is None:
                msg = "missing code/state."
                raise ValueError(msg)

            return AuthorizationResult(code=code, state=state)

    msg = "invalid authorization response."
    raise ValueError(msg)


def _parse_authorization_url(result: str) -> dict[str, str] | None:
    parsed = urllib.parse.urlsplit(result)
    query = parsed.query or parsed.fragment
    if not query:
        return None

    return dict(urllib.parse.parse_qsl(query, keep_blank_values=True))


def _parse_base64_query_string(result: str) -> dict[str, str] | None:
    try:
        padded_result = result + "=" * (-len(result) % 4)
        decoded_result = base64.urlsafe_b64decode(padded_result).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    return dict(urllib.parse.parse_qsl(decoded_result, keep_blank_values=True))


def exchange_code_request(code: str, verifier: str) -> requests.Request:
    return requests.Request(
        "POST",
        "https://accounts.spotify.com/api/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
