import base64
from dataclasses import dataclass

import pytest

from mopidy_spotify import pkce


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
