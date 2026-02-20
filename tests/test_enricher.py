"""Tests for the enricher module — parsing logic (no real HTTP calls)."""
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

import enricher
from enricher import (
    _extract_emails,
    _extract_tagline,
    _extract_founder_name,
    score_lead,
)


# ------------------------------------------------------------------ #
# _extract_tagline                                                    #
# ------------------------------------------------------------------ #

def test_extract_tagline_from_meta_description():
    html = '<html><head><meta name="description" content="The best tool for indie makers."></head><body></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_tagline(soup) == "The best tool for indie makers."


def test_extract_tagline_falls_back_to_og_description():
    html = '<html><head><meta property="og:description" content="Build faster, ship sooner."></head><body></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_tagline(soup) == "Build faster, ship sooner."


def test_extract_tagline_prefers_meta_over_og():
    html = (
        '<html><head>'
        '<meta name="description" content="Primary tagline.">'
        '<meta property="og:description" content="OG tagline.">'
        '</head><body></body></html>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_tagline(soup) == "Primary tagline."


def test_extract_tagline_returns_none_when_missing():
    soup = BeautifulSoup("<html><body><p>No meta here.</p></body></html>", "html.parser")
    assert _extract_tagline(soup) is None


def test_extract_tagline_caps_at_200_chars():
    long_content = "x" * 300
    html = f'<html><head><meta name="description" content="{long_content}"></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_tagline(soup)
    assert result is not None and len(result) <= 200


# ------------------------------------------------------------------ #
# _extract_founder_name                                               #
# ------------------------------------------------------------------ #

def test_extract_founder_name_founded_by():
    html = "<html><body><p>Founded by Jane Smith in 2021.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_founder_name(soup) == "Jane Smith"


def test_extract_founder_name_built_by():
    html = "<html><body><p>Built by Alex Chen, a solo developer.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_founder_name(soup) == "Alex Chen"


def test_extract_founder_name_ceo_label():
    html = "<html><body><p>CEO: Maria Lopez</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_founder_name(soup) == "Maria Lopez"


def test_extract_founder_name_hi_im():
    html = "<html><body><p>Hi! I'm Taylor running this solo.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_founder_name(soup)
    assert result is not None and "Taylor" in result


def test_extract_founder_name_returns_none_when_absent():
    html = "<html><body><p>Welcome to our product. No founder info here.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_founder_name(soup) is None


# ------------------------------------------------------------------ #
# _extract_emails                                                     #
# ------------------------------------------------------------------ #

def test_extract_emails_from_mailto_link():
    html = '<html><body><a href="mailto:hello@acme.com">Contact us</a></body></html>'
    emails = _extract_emails(html, "acme.com")
    assert "hello@acme.com" in emails


def test_extract_emails_on_domain_floats_first():
    html = (
        '<html><body>'
        '<a href="mailto:support@third-party.com">Support</a>'
        '<a href="mailto:team@acme.com">Team</a>'
        '</body></html>'
    )
    emails = _extract_emails(html, "acme.com")
    assert emails[0] == "team@acme.com"


def test_extract_emails_filters_noreply():
    html = '<html><body><a href="mailto:noreply@acme.com">No reply</a></body></html>'
    emails = _extract_emails(html, "acme.com")
    assert "noreply@acme.com" not in emails


def test_extract_emails_filters_privacy():
    html = '<html><body><a href="mailto:privacy@acme.com">Privacy</a></body></html>'
    emails = _extract_emails(html, "acme.com")
    assert "privacy@acme.com" not in emails


def test_extract_emails_deduplicates():
    html = (
        '<html><body>'
        '<a href="mailto:hello@acme.com">A</a>'
        '<a href="mailto:hello@acme.com">B</a>'
        '</body></html>'
    )
    emails = _extract_emails(html, "acme.com")
    assert emails.count("hello@acme.com") == 1


def test_extract_emails_returns_empty_when_none():
    html = "<html><body><p>Contact us via phone only.</p></body></html>"
    emails = _extract_emails(html, "acme.com")
    assert emails == []


# ------------------------------------------------------------------ #
# score_lead                                                          #
# ------------------------------------------------------------------ #

def test_score_no_signals_gives_base():
    score = score_lead(None, "", False, False)
    assert score == 25


def test_score_with_email():
    score = score_lead("hello@acme.com", "", False, False)
    assert score == 60  # 25 base + 35 email


def test_score_maxes_at_100():
    score = score_lead(
        "hello@acme.com",
        "newsletter community blog indie bootstrapped tool saas",
        True,   # tagline
        True,   # founder
    )
    assert score <= 100


def test_score_newsletter_signal():
    score_with    = score_lead(None, "runs a popular newsletter for developers", False, False)
    score_without = score_lead(None, "builds a calendar app", False, False)
    assert score_with > score_without


def test_score_indie_signal():
    score_with    = score_lead(None, "indie bootstrapped founder", False, False)
    score_without = score_lead(None, "enterprise SaaS product", False, False)
    assert score_with > score_without


def test_score_full_profile():
    score = score_lead(
        "jane@example.com",           # email: +35
        "newsletter audience indie",   # audience: +10, indie: +5
        True,                          # tagline: +10
        True,                          # founder: +10
    )
    # 25 + 35 + 10 + 5 + 10 + 10 = 95
    assert score == 95


# ------------------------------------------------------------------ #
# _fetch — network layer (mocked)                                     #
# ------------------------------------------------------------------ #

def test_fetch_returns_html_on_success():
    import requests
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>OK</body></html>"

    with patch("enricher.requests.get", return_value=mock_resp):
        result = enricher._fetch("https://example.com")

    assert result == "<html><body>OK</body></html>"


def test_fetch_returns_none_on_404():
    import requests
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("enricher.requests.get", return_value=mock_resp):
        result = enricher._fetch("https://example.com")

    assert result is None


def test_fetch_returns_none_on_connection_error():
    import requests
    with patch("enricher.requests.get", side_effect=requests.ConnectionError("timeout")), \
         patch("enricher.time.sleep"):
        result = enricher._fetch("https://example.com", retries=2)

    assert result is None
