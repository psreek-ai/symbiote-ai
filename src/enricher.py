"""Enricher Module: visits company websites to extract deeper context for personalization.

Pipeline position: Stage 1b — runs after Scout, before Negotiate.

What it extracts per lead:
- Tagline     : <meta name="description"> content — a specific sentence to quote in the hook
- Founder name: pattern-matched from About/Team page text
- Contact email: discovered via mailto: links and text-pattern search on homepage + /about
- Lead score   : 0–100 quality signal used by Negotiate to skip low-value leads

Design notes:
- Fetches homepage + a set of common contact/about paths
- Prioritises on-domain emails (e.g. hello@acme.com over 3rd-party support tools)
- Uses regex founder patterns found on real About pages
- Scoring caps at 100; MIN_LEAD_SCORE filters are enforced in Negotiate, not here
- All HTTP failures are non-fatal; the lead is enriched with whatever was found
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

from config import Config
from db import get_connection
from logger import get_logger

log = get_logger("enricher")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SymbioteEnricherBot/1.0; +https://symbiote.ai/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_TIMEOUT = 12
# Paths to try when hunting for contact emails or founder names
_SECONDARY_PATHS = ["/about", "/team", "/contact", "/founders", "/hello", "/us"]

# Emails from these domains/prefixes are noise — skip them
_EMAIL_JUNK_PATTERNS = (
    "noreply@", "no-reply@", "privacy@", "legal@", "security@",
    "@sentry.io", "@gravatar.com", "@example.com", "@w3.org",
)


# ------------------------------------------------------------------ #
# Low-level helpers                                                   #
# ------------------------------------------------------------------ #

def _fetch(url: str, retries: int = 2) -> str | None:
    """Fetch a URL silently. Returns HTML string or None on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            return None  # 4xx/5xx — no retry benefit
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                log.debug(f"Fetch failed for {url}: {e}")
    return None


def _extract_emails(html: str, base_domain: str) -> list[str]:
    """Return emails found in HTML, on-domain emails first, noise filtered."""
    soup = BeautifulSoup(html, "html.parser")

    # mailto: links are the most reliable source
    mailto_emails: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip().lower()
            if "@" in addr:
                mailto_emails.append(addr)

    # Text-based regex as fallback
    text_emails = re.findall(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",
        soup.get_text(),
    )
    text_emails = [e.lower() for e in text_emails]

    # Merge, deduplicate, filter noise
    seen: set[str] = set()
    combined: list[str] = []
    for email in mailto_emails + text_emails:
        if email in seen:
            continue
        seen.add(email)
        if any(email.startswith(p) or p in email for p in _EMAIL_JUNK_PATTERNS):
            continue
        combined.append(email)

    # Sort: on-domain emails float to the top
    on_domain = [e for e in combined if base_domain in e]
    off_domain = [e for e in combined if base_domain not in e]
    return on_domain + off_domain


def _extract_tagline(soup: BeautifulSoup) -> str | None:
    """Return the meta description, capped at 200 chars."""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return str(meta["content"]).strip()[:200]
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return str(og["content"]).strip()[:200]
    return None


def _extract_founder_name(soup: BeautifulSoup) -> str | None:
    """Pattern-match common founder attribution phrases from page text."""
    text = soup.get_text(" ", strip=True)
    patterns = [
        r"[Ff]ounded by ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Bb]uilt by ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Mm]ade by ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Cc]reated by ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Cc][Ee][Oo]\s*[:\-–]\s*([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Ff]ounder\s*[:\-–]\s*([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Hh]i[,!]?\s+I(?:'m| am) ([A-Z][a-z]+)",  # "Hi, I'm Alex"
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None


def score_lead(
    contact_email: str | None,
    context_notes: str,
    has_tagline: bool,
    has_founder: bool,
) -> int:
    """Score a lead's partnership potential from 0–100.

    Scoring rationale:
    - Email is the gating factor: without it we can't pitch at all (+35)
    - Tagline lets us write a specific hook (+10)
    - Founder name lets us personalise the greeting (+10)
    - Audience/newsletter signals → high swap potential (+up to 10)
    - Indie/bootstrapped signals → receptive to non-paid partnerships (+up to 10)
    """
    score = 25  # base

    if contact_email:
        score += 35
    if has_tagline:
        score += 10
    if has_founder:
        score += 10

    notes_lower = (context_notes or "").lower()

    for kw in ("newsletter", "community", "blog", "podcast", "audience", "subscriber"):
        if kw in notes_lower:
            score += 10
            break

    for kw in ("indie", "bootstrapped", "solo", "maker", "independent", "open source"):
        if kw in notes_lower:
            score += 5
            break

    for kw in ("tool", "app", "saas", "extension", "plugin", "api", "platform"):
        if kw in notes_lower:
            score += 5
            break

    return min(score, 100)


# ------------------------------------------------------------------ #
# Main enrichment function                                            #
# ------------------------------------------------------------------ #

def enrich_leads() -> int:
    """Visit each unenriched scouted lead's website and extract context.

    Updates: context_notes (appended), founder_name, score, enriched_at,
             contact_email (if discovered and currently null).

    Returns the number of leads successfully enriched.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, company_name, url, contact_email, context_notes
        FROM companies
        WHERE status = 'scouted' AND enriched_at IS NULL AND opted_out_at IS NULL
    """)
    leads = cursor.fetchall()

    if not leads:
        log.info("No leads pending enrichment.")
        conn.close()
        return 0

    log.info(f"Enriching {len(leads)} lead(s).")
    enriched = 0

    for lead in leads:
        lead_id       = lead["id"]
        company_name  = lead["company_name"]
        url           = lead["url"]
        contact_email = lead["contact_email"]
        context_notes = lead["context_notes"] or ""

        log.info(f"Enriching '{company_name}' at {url}")

        try:
            parsed = urlparse(url)
            base_domain = parsed.netloc.lower().removeprefix("www.")
        except Exception:
            base_domain = ""

        # --- Homepage ---
        homepage_html = _fetch(url)
        tagline      : str | None = None
        founder_name : str | None = None
        found_email  : str | None = None

        if homepage_html:
            soup = BeautifulSoup(homepage_html, "html.parser")
            tagline = _extract_tagline(soup)
            founder_name = _extract_founder_name(soup)
            if not contact_email:
                emails = _extract_emails(homepage_html, base_domain)
                found_email = emails[0] if emails else None

        # --- Secondary pages (about, contact, team…) ---
        if not founder_name or (not contact_email and not found_email):
            for path in _SECONDARY_PATHS:
                secondary_url = urljoin(url, path)
                secondary_html = _fetch(secondary_url)
                if not secondary_html:
                    continue
                sec_soup = BeautifulSoup(secondary_html, "html.parser")

                if not founder_name:
                    founder_name = _extract_founder_name(sec_soup)

                if not contact_email and not found_email:
                    emails = _extract_emails(secondary_html, base_domain)
                    found_email = emails[0] if emails else None

                if founder_name and (contact_email or found_email):
                    break  # found everything we need

        # --- Score ---
        effective_email = contact_email or found_email
        lead_score = score_lead(effective_email, context_notes, bool(tagline), bool(founder_name))

        # --- Append enriched data to context_notes ---
        additions: list[str] = []
        if tagline:
            additions.append(f"Tagline: {tagline}")
        if founder_name:
            additions.append(f"Founder: {founder_name}")
        enriched_notes = (context_notes + " | " + " | ".join(additions)) if additions else context_notes

        cursor.execute("""
            UPDATE companies
            SET contact_email = COALESCE(contact_email, ?),
                context_notes = ?,
                founder_name  = ?,
                score         = ?,
                enriched_at   = datetime('now'),
                updated_at    = datetime('now')
            WHERE id = ?
        """, (found_email, enriched_notes, founder_name, lead_score, lead_id))
        conn.commit()

        log.info(
            f"  Score {lead_score}/100 | "
            f"Email: {effective_email or 'not found'} | "
            f"Founder: {founder_name or 'unknown'} | "
            f"Tagline: {'yes' if tagline else 'no'}"
        )
        enriched += 1

    conn.close()
    log.info(f"Enrichment complete. {enriched} lead(s) processed.")
    return enriched


if __name__ == "__main__":
    enrich_leads()
