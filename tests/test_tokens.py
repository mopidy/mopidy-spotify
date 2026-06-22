import base64

import pytest

from mopidy_spotify import tokens


def test_parse_authorization_result_parses_redirect_url() -> None:
    result = tokens.parse_authorization_result(
        "https://example.com/callback?code=code-123&state=state-123"
    )

    assert result == tokens.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_parses_base64_query_string() -> None:
    payload = (
        base64.urlsafe_b64encode(b"code=code-123&state=state-123")
        .decode("ascii")
        .rstrip("=")
    )

    result = tokens.parse_authorization_result(payload)

    assert result == tokens.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_raises_on_provider_error() -> None:
    with pytest.raises(ValueError, match="access_denied"):
        tokens.parse_authorization_result(
            "https://example.com/callback?error=access_denied&error_description=Denied"
        )
