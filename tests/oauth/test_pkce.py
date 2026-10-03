import base64
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest

from mopidy_spotify.oauth import pkce


def test_generate_pkce_verifier_matches_rfc7636_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RFC 7636 Appendix B provides an independent S256 test vector.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    monkeypatch.setattr(pkce.secrets, "token_urlsafe", lambda _: verifier)

    assert pkce.generate_pkce_verifier() == (
        verifier,
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    )


def test_generate_pkce_verifier_uses_protocol_safe_length_and_characters() -> None:
    verifier, challenge = pkce.generate_pkce_verifier()

    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge)


def test_generate_authorization_url_preserves_pkce_parameters() -> None:
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    state = "state+/=&?"

    url = urlsplit(pkce.generate_authorization_url(challenge, state))
    query = parse_qs(url.query)

    assert (url.scheme, url.netloc, url.path) == (
        "https",
        "accounts.spotify.com",
        "/authorize",
    )
    assert not url.fragment
    assert query == {
        "client_id": [pkce.CLIENT_ID],
        "response_type": ["code"],
        "redirect_uri": [pkce.REDIRECT_URI],
        "code_challenge_method": ["S256"],
        "code_challenge": [challenge],
        "state": [state],
        "scope": [" ".join(pkce.SCOPES)],
    }


def test_exchange_code_request_encodes_authorization_code_and_verifier() -> None:
    code = "code+/=&?"
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    request = pkce.exchange_code_request(code, verifier).prepare()

    assert request.method == "POST"
    assert request.url == "https://accounts.spotify.com/api/token"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert isinstance(request.body, str)
    assert parse_qs(request.body) == {
        "client_id": [pkce.CLIENT_ID],
        "grant_type": ["authorization_code"],
        "code": [code],
        "redirect_uri": [pkce.REDIRECT_URI],
        "code_verifier": [verifier],
    }


def test_parse_authorization_result_parses_redirect_url() -> None:
    result = pkce.parse_authorization_result(
        "https://example.com/callback?code=code-123&state=state-123"
    )

    assert result == pkce.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_parses_base64_query_string() -> None:
    payload = (
        base64.urlsafe_b64encode(b"code=code-123&state=state-123")
        .decode("ascii")
        .rstrip("=")
    )

    result = pkce.parse_authorization_result(payload)

    assert result == pkce.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_raises_on_provider_error() -> None:
    with pytest.raises(ValueError, match="access_denied"):
        pkce.parse_authorization_result(
            "https://example.com/callback?error=access_denied&error_description=Denied"
        )


@dataclass(frozen=True, kw_only=True)
class ParseAuthorizationResultScenario:
    name: str
    input_value: str
    expected: pkce.AuthorizationResult | None = None
    error: str | None = None


@pytest.mark.parametrize(
    ("scenario"),
    [
        ParseAuthorizationResultScenario(
            name="empty input",
            input_value="",
            error="invalid authorization response.",
        ),
        ParseAuthorizationResultScenario(
            name="bad base64 padding",
            input_value="a",
            error="invalid authorization response.",
        ),
        ParseAuthorizationResultScenario(
            name="missing query params",
            input_value="https://example.com/callback",
            error="invalid authorization response.",
        ),
        ParseAuthorizationResultScenario(
            name="whitespace trimmed",
            input_value=(
                "  https://example.com/callback?code=code-123&state=state-123  "
            ),
            expected=pkce.AuthorizationResult(code="code-123", state="state-123"),
        ),
        ParseAuthorizationResultScenario(
            name="error without description",
            input_value="https://example.com/callback?error=access_denied",
            error="access_denied",
        ),
        ParseAuthorizationResultScenario(
            name="missing code",
            input_value="https://example.com/callback?state=state-123",
            error="missing code/state.",
        ),
        ParseAuthorizationResultScenario(
            name="missing state",
            input_value="https://example.com/callback?code=code-123",
            error="missing code/state.",
        ),
    ],
    ids=lambda scenario: scenario.name,
)
def test_parse_authorization_result_edge_cases(
    scenario: ParseAuthorizationResultScenario,
) -> None:
    if scenario.error is not None:
        with pytest.raises(ValueError, match=scenario.error):
            pkce.parse_authorization_result(scenario.input_value)
    else:
        assert (
            pkce.parse_authorization_result(scenario.input_value) == scenario.expected
        )
