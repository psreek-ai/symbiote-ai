"""Tests for the negotiate module — email drafting logic (LLM calls mocked)."""
import json
import pytest
from unittest.mock import MagicMock, patch

import negotiate


# ------------------------------------------------------------------ #
# _draft_email                                                        #
# ------------------------------------------------------------------ #

def _make_client(response_text: str) -> MagicMock:
    """Build a mock Anthropic client that returns *response_text* as content."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = mock_msg
    return client


def test_draft_email_returns_subject_and_body():
    payload = json.dumps({"subject": "Quick collab idea?", "body": "Hey Acme, great tool. Our audiences overlap. Open to a swap?"})
    client = _make_client(payload)

    subject, body = negotiate._draft_email(client, "Acme", "https://acme.com", "A dev tool")

    assert subject == "Quick collab idea?"
    assert "Acme" in body or "swap" in body.lower()


def test_draft_email_strips_markdown_fences():
    payload = "```json\n" + json.dumps({"subject": "Hey!", "body": "Three sentences here."}) + "\n```"
    client = _make_client(payload)

    subject, body = negotiate._draft_email(client, "Acme", "https://acme.com", "")

    assert subject == "Hey!"
    assert body == "Three sentences here."


def test_draft_email_falls_back_after_api_failure():
    """All retries exhaust → fallback template is returned, never raises."""
    import anthropic
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

    subject, body = negotiate._draft_email(client, "Acme", "https://acme.com", "", retries=2)

    assert isinstance(subject, str) and len(subject) > 0
    assert isinstance(body, str) and len(body) > 0


def test_draft_email_falls_back_on_json_error():
    """Bad JSON from the LLM triggers immediate fallback (no retry loop)."""
    client = _make_client("this is not json at all")

    subject, body = negotiate._draft_email(client, "Zeta", "https://zeta.io", "")

    assert "Zeta" in subject or "Zeta" in body


# ------------------------------------------------------------------ #
# _fallback_email                                                     #
# ------------------------------------------------------------------ #

def test_fallback_email_contains_company_name():
    subject, body = negotiate._fallback_email("Acme", "https://acme.com")
    assert "Acme" in subject or "Acme" in body


def test_fallback_email_never_mentions_money():
    subject, body = negotiate._fallback_email("Acme", "https://acme.com")
    combined = (subject + " " + body).lower()
    for banned in ("money", "pay", "compensation", "revenue", "equity", "$"):
        assert banned not in combined, f"Fallback email contains banned word: '{banned}'"
