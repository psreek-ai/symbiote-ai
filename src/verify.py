"""Verify Module: confirms Symbiote AI link/widget placement on partner websites.

Pipeline position: Stage 3 of 3
Input:  companies with status='pitched' or 'negotiating'
Output: status updated to 'live' when the placement is confirmed; context_notes annotated

Detection strategy (in order of confidence):
1. <a href> pointing to our domain          — direct backlink
2. <img src> referencing our domain         — banner/logo placement
3. <iframe src> referencing our domain      — widget embed
4. Plain-text brand mention in page body    — softest signal, still useful

Fetching uses a bot-friendly User-Agent and follows up to 10 redirects.
Three retries with exponential back-off on network errors.
"""

import time
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


def _fetch_html(url: str, retries: int = 3) -> str | None:
    """Fetch page HTML with retry logic. Returns None if all attempts fail."""
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
        except requests.HTTPError as e:
            log.warning(f"HTTP {e.response.status_code} fetching {url}. No retry.")
            return None  # HTTP errors are deterministic; retrying won't help
        except requests.RequestException as e:
            wait = 2 ** attempt
            log.warning(f"Fetch error for {url} (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait}s.")
            time.sleep(wait)
    return None


def _check_placement(html: str, domain: str) -> tuple[bool, str]:
    """Parse HTML and search for any reference to *domain*.

    Returns (found, human_readable_description).
    """
    soup = BeautifulSoup(html, "html.parser")
    domain_lower = domain.lower()
    brand = domain_lower.split(".")[0].capitalize()  # e.g. "symbiote.ai" → "Symbiote"

    # 1. Direct backlink
    for tag in soup.find_all("a", href=True):
        if domain_lower in tag["href"].lower():
            return True, f"Backlink found: <a href='{tag['href']}'>"

    # 2. Image / logo
    for tag in soup.find_all("img", src=True):
        if domain_lower in tag["src"].lower():
            return True, f"Image asset found: <img src='{tag['src']}'>"

    # 3. Embedded widget
    for tag in soup.find_all("iframe", src=True):
        if domain_lower in tag["src"].lower():
            return True, f"Widget iframe found: <iframe src='{tag['src']}'>"

    # 4. Plain-text brand mention
    page_text = soup.get_text(" ", strip=True).lower()
    idx = page_text.find(brand.lower())
    if idx != -1:
        snippet = page_text[max(0, idx - 30): idx + 60].strip()
        return True, f"Brand mention: '...{snippet}...'"

    return False, f"No reference to '{domain}' found on this page."


def verify_placements() -> tuple[int, int]:
    """Check all pitched/negotiating partner sites for Symbiote AI placement.

    Returns:
        (verified_count, total_checked)  — e.g. (3, 5) means 3 of 5 sites are live.
    """
    log.info("Starting placement verification.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, company_name, url FROM companies WHERE status IN ('pitched', 'negotiating')"
    )
    targets = cursor.fetchall()

    if not targets:
        log.info("No leads in 'pitched' or 'negotiating' status to verify.")
        conn.close()
        return 0, 0

    log.info(f"Checking {len(targets)} partner site(s) for Symbiote AI placement.")
    verified = 0

    for target in targets:
        lead_id = target["id"]
        company_name = target["company_name"]
        url = target["url"]

        log.info(f"Fetching {company_name} at {url}")
        html = _fetch_html(url)
        if html is None:
            log.warning(f"  Could not fetch {url}. Skipping.")
            continue

        found, description = _check_placement(html, Config.SYMBIOTE_DOMAIN)

        if found:
            log.info(f"  VERIFIED: {description}")
            cursor.execute(
                """
                UPDATE companies
                SET status        = 'live',
                    context_notes = context_notes || ' | Verified: ' || ?,
                    verified_at   = datetime('now'),
                    updated_at    = datetime('now')
                WHERE id = ?
                """,
                (description, lead_id),
            )
            verified += 1
        else:
            log.info(f"  Not found: {description}")
            cursor.execute(
                """
                UPDATE companies
                SET context_notes = context_notes || ' | Verification attempted: not found.',
                    updated_at    = datetime('now')
                WHERE id = ?
                """,
                (lead_id,),
            )

        conn.commit()

    conn.close()
    log.info(f"Verification complete. {verified}/{len(targets)} partner(s) confirmed live.")
    return verified, len(targets)


if __name__ == "__main__":
    verify_placements()
