"""Tests for the followup module — draft logic (LLM calls mocked)."""
import json
import pytest
from unittest.mock import MagicMock, patch

import followup
from followup import _draft_followup, _make_fallback


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _make_client(response_text: str) -> MagicMock:
    """Build a mock Anthropic client returning *response_text*."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = mock_msg
    return client


# ------------------------------------------------------------------ #
# _make_fallback                                                      #
# ------------------------------------------------------------------ #

def test_fallback_1_subject_starts_with_re():
    subject, body = _make_fallback(1, "Quick collab idea?")
    assert subject.startswith("Re: ")


def test_fallback_2_subject_starts_with_re():
    subject, body = _make_fallback(2, "Partnership swap")
    assert subject.startswith("Re: ")


def test_fallback_1_body_is_nonempty():
    _, body = _make_fallback(1, "any subject")
    assert isinstance(body, str) and len(body) > 10


def test_fallback_2_body_is_nonempty():
    _, body = _make_fallback(2, "any subject")
    assert isinstance(body, str) and len(body) > 10


def test_fallback_never_mentions_money():
    for num in (1, 2):
        subject, body = _make_fallback(num, "test subject")
        combined = (subject + " " + body).lower()
        for banned in ("money", "pay", "compensation", "revenue", "equity", "$"):
            assert banned not in combined, f"Follow-up #{num} fallback mentions banned word: '{banned}'"


def test_fallback_unknown_number_uses_fallback_1():
    subject_unk, _ = _make_fallback(99, "original subject")
    subject_1,   _ = _make_fallback(1,  "original subject")
    assert subject_unk == subject_1


# ------------------------------------------------------------------ #
# _draft_followup — happy path                                        #
# ------------------------------------------------------------------ #

def test_draft_followup_returns_subject_and_body():
    payload = json.dumps({
        "subject": "Re: Quick collab idea?",
        "body": "Just bumping this up — still think there's a great fit.",
    })
    client = _make_client(payload)

    subject, body = _draft_followup(client, "Acme", "Quick collab idea?", follow_up_num=1)

    assert subject.startswith("Re: ")
    assert isinstance(body, str) and len(body) > 0


def test_draft_followup_strips_markdown_fences():
    payload = "```json\n" + json.dumps({
        "subject": "Re: Hey!",
        "body": "Just checking in.",
    }) + "\n```"
    client = _make_client(payload)

    subject, body = _draft_followup(client, "Acme", "Hey!", follow_up_num=1)

    assert subject == "Re: Hey!"
    assert body == "Just checking in."


def test_draft_followup_fallback_on_json_error():
    """Bad JSON → immediate fallback, no crash."""
    client = _make_client("this is definitely not json")

    subject, body = _draft_followup(client, "Zeta", "Partnership swap", follow_up_num=1)

    assert isinstance(subject, str) and subject.startswith("Re: ")
    assert isinstance(body, str) and len(body) > 0


def test_draft_followup_fallback_after_api_failure():
    """API errors exhaust retries → hardcoded fallback."""
    import anthropic
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

    with patch("followup.time.sleep"):
        subject, body = _draft_followup(
            client, "Beta Corp", "Quick collab idea?", follow_up_num=2, retries=2
        )

    assert subject.startswith("Re: ")
    assert isinstance(body, str) and len(body) > 0


def test_draft_followup_num_2_uses_subject():
    payload = json.dumps({
        "subject": "Re: Audience swap",
        "body": "Last nudge — no pressure.",
    })
    client = _make_client(payload)

    subject, body = _draft_followup(client, "Co", "Audience swap", follow_up_num=2)

    assert "Audience swap" in subject


# ------------------------------------------------------------------ #
# Content guardrails (mirroring negotiate tests)                      #
# ------------------------------------------------------------------ #

def test_draft_followup_result_never_mentions_money():
    payload = json.dumps({
        "subject": "Re: Quick collab",
        "body": "Just checking in on the collab idea.",
    })
    client = _make_client(payload)

    subject, body = _draft_followup(client, "Acme", "Quick collab", follow_up_num=1)
    combined = (subject + " " + body).lower()

    for banned in ("money", "pay", "compensation", "revenue", "equity", "$"):
        assert banned not in combined, f"Follow-up mentions banned word: '{banned}'"
