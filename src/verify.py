"""Verify Module: confirms Symbiote AI link/widget placement on partner websites.

Pipeline position: Stage 4 of 4 (Scout → Enrich → Negotiate → Verify)
Input:  companies with status='pitched' or 'negotiating'
Output: status updated to 'live' on confirmed placement; context_notes annotated

Improvements over v1:
- Domain-exact matching via urlparse netloc comparison — "notsymbiote.ai"
  no longer falsely matches when domain="symbiote.ai"
- Checks multiple pages: homepage + /partners + /integrations + /about
  so partner directory pages are found even when the homepage has no mention
- All four detection signals retained: backlinks, images, iframes, brand text

Fetch policy:
- Bot-friendly User-Agent with contact URL in comment
- 15-second timeout; follows redirects
- 3 retries with exponential back-off on transient errors
- HTTP 4xx/5xx → immediate bail (retrying won't help)
"""

import time
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from config import Config
from db import get_connection
from logger import get_logger

load_dotenv()
log = get_logger("verify")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SymbioteVerificationBot/1.0; "
        "+https://symbiote.ai/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_TIMEOUT_SECONDS = 15

# Additional paths to check beyond the homepage
_EXTRA_PATHS = ["/partners", "/integrations", "/about"]


# ------------------------------------------------------------------ #
# Domain matching (fixed)                                             #
# ------------------------------------------------------------------ #

def _url_matches_domain(url_str: str, domain: str) -> bool:
    """Return True if url_str belongs to domain or any subdomain of it.

    Uses netloc comparison — "notsymbiote.ai" does NOT match "symbiote.ai".
    """
    try:
        netloc = urlparse(url_str).netloc.lower().removeprefix("www.")
        return netloc == domain or netloc.endswith("." + domain)
    except Exception:
        return False


# ------------------------------------------------------------------ #
# HTTP layer                                                          #
# ------------------------------------------------------------------ #

def _fetch_html(url: str, retries: int = 3) -> str | None:
    """Fetch page HTML with retry logic. Returns None on all failures."""
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError:
            return None  # 4xx/5xx are deterministic; no retry
        except requests.RequestException as e:
            wait = 2 ** attempt
            log.warning(
                f"Fetch error for {url} (attempt {attempt + 1}/{retries}): {e}. "
                f"Retrying in {wait}s."
            )
            time.sleep(wait)
    return None


# ------------------------------------------------------------------ #
# Placement detection                                                 #
# ------------------------------------------------------------------ #

def _check_placement(html: str, domain: str) -> tuple[bool, str]:
    """Parse HTML and search for any reference to domain.

    Signals (descending confidence):
      1. <a href>    pointing to our domain — direct backlink
      2. <img src>   referencing our domain — logo/banner
      3. <iframe src> referencing our domain — widget embed
      4. Brand name in plain text           — softest signal

    Returns (found, human_readable_description).
    """
    soup  = BeautifulSoup(html, "html.parser")
    brand = domain.split(".")[0].capitalize()  # "symbiote.ai" → "Symbiote"

    for tag in soup.find_all("a", href=True):
        if _url_matches_domain(tag["href"], domain):
            return True, f"Backlink found: <a href='{tag['href']}'>"

    for tag in soup.find_all("img", src=True):
        if _url_matches_domain(tag["src"], domain):
            return True, f"Image asset found: <img src='{tag['src']}'>"

    for tag in soup.find_all("iframe", src=True):
        if _url_matches_domain(tag["src"], domain):
            return True, f"Widget iframe found: <iframe src='{tag['src']}'>"

    page_text = soup.get_text(" ", strip=True).lower()
    idx = page_text.find(brand.lower())
    if idx != -1:
        snippet = page_text[max(0, idx - 30): idx + 60].strip()
        return True, f"Brand mention: '...{snippet}...'"

    return False, f"No reference to '{domain}' found."


# ------------------------------------------------------------------ #
# Main                                                                #
# ------------------------------------------------------------------ #

def verify_placements() -> tuple[int, int]:
    """Check all pitched/negotiating partner sites for Symbiote AI placement.

    Checks homepage + /partners + /integrations + /about on each partner site.
    Updates status to 'live' on the first confirmed match on any page.

    Returns:
        (verified_count, total_checked)
    """
    log.info("Starting placement verification.")

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, company_name, url FROM companies WHERE status IN ('pitched', 'negotiating')"
    )
    targets = cursor.fetchall()

    if not targets:
        log.info("No leads in 'pitched' or 'negotiating' status to verify.")
        conn.close()
        return 0, 0

    log.info(f"Checking {len(targets)} partner site(s).")
    verified = 0

    for target in targets:
        lead_id      = target["id"]
        company_name = target["company_name"]
        base_url     = target["url"].rstrip("/")

        pages_to_check = [base_url] + [base_url + path for path in _EXTRA_PATHS]
        found       = False
        description = ""

        for page_url in pages_to_check:
            log.info(f"  Checking {company_name} → {page_url}")
            html = _fetch_html(page_url)
            if html is None:
                log.debug(f"    Could not fetch {page_url}.")
                continue

            found, description = _check_placement(html, Config.SYMBIOTE_DOMAIN)
            if found:
                log.info(f"    VERIFIED: {description}")
                break
            log.debug(f"    Not found on {page_url}.")

        if found:
            cursor.execute("""
                UPDATE companies
                SET status        = 'live',
                    context_notes = context_notes || ' | Verified: ' || ?,
                    verified_at   = datetime('now'),
                    updated_at    = datetime('now')
                WHERE id = ?
            """, (description, lead_id))
            verified += 1
        else:
            log.info(f"  {company_name}: not found across {len(pages_to_check)} page(s).")
            cursor.execute("""
                UPDATE companies
                SET context_notes = context_notes || ' | Verification: not found.',
                    updated_at    = datetime('now')
                WHERE id = ?
            """, (lead_id,))

        conn.commit()

    conn.close()
    log.info(f"Verification complete. {verified}/{len(targets)} partner(s) confirmed live.")
    return verified, len(targets)


if __name__ == "__main__":
    verify_placements()
