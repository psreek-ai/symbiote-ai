"""Tests for the scout module — extraction and dedup logic (API calls mocked)."""
import json
import pytest
from unittest.mock import MagicMock, patch

import scout
from scout import _parse_json_from_response, _extract_company, CompanyExtract


# ------------------------------------------------------------------ #
# _parse_json_from_response                                           #
# ------------------------------------------------------------------ #

def test_parse_plain_json():
    raw = '{"company_name": "Acme", "url": "https://acme.com", "contact_email": null, "context_notes": "A tool."}'
    data = _parse_json_from_response(raw)
    assert data["company_name"] == "Acme"
    assert data["contact_email"] is None


def test_parse_strips_backtick_fences():
    inner = '{"company_name": "Zeta", "url": "https://zeta.io", "contact_email": null, "context_notes": "A SaaS."}'
    raw = f"```\n{inner}\n```"
    data = _parse_json_from_response(raw)
    assert data["company_name"] == "Zeta"


def test_parse_strips_json_language_tag():
    inner = '{"company_name": "Beta", "url": "https://beta.io", "contact_email": null, "context_notes": "B."}'
    raw = f"```json\n{inner}\n```"
    data = _parse_json_from_response(raw)
    assert data["company_name"] == "Beta"


def test_parse_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_json_from_response("this is not json")


# ------------------------------------------------------------------ #
# _extract_company                                                    #
# ------------------------------------------------------------------ #

def _make_claude_client(response_text: str) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = mock_msg
    return client


def test_extract_company_happy_path():
    payload = json.dumps({
        "company_name": "Indie Tools",
        "url": "https://indie.tools",
        "contact_email": "hello@indie.tools",
        "context_notes": "A newsletter for indie makers.",
    })
    client = _make_claude_client(payload)
    result = _extract_company(client, {
        "title": "Indie Tools",
        "url": "https://indie.tools",
        "content": "Newsletter for indie makers.",
    })
    assert isinstance(result, CompanyExtract)
    assert result.company_name == "Indie Tools"
    assert result.url == "https://indie.tools"
    assert result.contact_email == "hello@indie.tools"


def test_extract_company_with_null_email():
    payload = json.dumps({
        "company_name": "Solo App",
        "url": "https://soloapp.io",
        "contact_email": None,
        "context_notes": "A micro-SaaS for freelancers.",
    })
    client = _make_claude_client(payload)
    result = _extract_company(client, {"title": "Solo App", "url": "https://soloapp.io", "content": ""})
    assert result is not None
    assert result.contact_email is None


def test_extract_company_returns_none_on_json_error():
    client = _make_claude_client("not valid json at all")
    result = _extract_company(client, {"title": "X", "url": "https://x.com", "content": ""})
    assert result is None


def test_extract_company_returns_none_on_missing_required_field():
    # Missing 'url' field — Pydantic validation should fail
    payload = json.dumps({
        "company_name": "No URL",
        "contact_email": None,
        "context_notes": "Missing url field.",
    })
    client = _make_claude_client(payload)
    result = _extract_company(client, {"title": "No URL", "url": "", "content": ""})
    assert result is None


def test_extract_company_retries_on_api_status_error():
    import anthropic

    good_payload = json.dumps({
        "company_name": "Retry Corp",
        "url": "https://retry.io",
        "contact_email": None,
        "context_notes": "Survives retries.",
    })
    good_msg = MagicMock()
    good_msg.content = [MagicMock(text=good_payload)]

    client = MagicMock()
    error = anthropic.APIStatusError(
        "rate limit",
        response=MagicMock(status_code=429),
        body={},
    )
    # First call raises, second succeeds
    client.messages.create.side_effect = [error, good_msg]

    with patch("scout.time.sleep"):
        result = _extract_company(client, {"title": "Retry Corp", "url": "https://retry.io", "content": ""})

    assert result is not None
    assert result.company_name == "Retry Corp"


def test_extract_company_returns_none_after_exhausting_retries():
    import anthropic

    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

    with patch("scout.time.sleep"):
        result = _extract_company(
            client, {"title": "Gone", "url": "https://gone.io", "content": ""}, retries=2
        )

    assert result is None


# ------------------------------------------------------------------ #
# CompanyExtract — pydantic model                                     #
# ------------------------------------------------------------------ #

def test_company_extract_valid():
    ce = CompanyExtract(
        company_name="Acme",
        url="https://acme.com",
        contact_email=None,
        context_notes="Tool for developers.",
    )
    assert ce.company_name == "Acme"


def test_company_extract_rejects_missing_name():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CompanyExtract(
            url="https://acme.com",
            contact_email=None,
            context_notes="Tool.",
        )
