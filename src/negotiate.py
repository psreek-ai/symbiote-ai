"""Negotiate Module: drafts personalized partnership pitches and delivers them via email.

Pipeline position: Stage 3 of 4 (Scout → Enrich → Negotiate → Verify)
Input:  companies with status='scouted', score >= MIN_LEAD_SCORE, opted_out_at IS NULL
Output: outbound emails via Resend (HTML + plain text), status updated to 'pitched'

Key upgrades over v1:
- Reads enriched context: founder name (personalised greeting) + tagline (specific hook)
- Skips leads below Config.MIN_LEAD_SCORE — avoids burning sends on weak signals
- Sends both HTML and plain-text parts (better deliverability + rendering)
- Embeds a CAN-SPAM-compliant unsubscribe link in the footer (legally required)
- Stores email_subject + email_body for audit trail and follow-up threading
"""

import json
import time
from urllib.parse import quote as url_quote

from dotenv import load_dotenv
import resend
import anthropic

from config import Config
from db import get_connection
from logger import get_logger

load_dotenv()
log = get_logger("negotiate")

_SYSTEM_PROMPT = (
    "You are the Head of Partnerships at Symbiote AI, an autonomous business development platform. "
    "Your outreach style is casual, direct, and founder-to-founder. "
    "Write at a 6th-grade reading level. "
    "Never use corporate buzzwords (synergy, leverage, unlock, game-changing, revolutionary, delve). "
    "STRICT RULE: Never mention money, compensation, equity, or revenue share of any kind. "
    "We offer only audience exposure — a 1-to-1 swap."
)


# ------------------------------------------------------------------ #
# Context parsing                                                     #
# ------------------------------------------------------------------ #

def _parse_enriched_context(context_notes: str) -> dict[str, str | None]:
    """Extract structured fields appended by the Enricher from context_notes."""
    result: dict[str, str | None] = {"tagline": None, "founder_name": None}
    for part in (context_notes or "").split(" | "):
        if part.startswith("Tagline: "):
            result["tagline"] = part[9:].strip()
        elif part.startswith("Founder: "):
            result["founder_name"] = part[9:].strip()
    return result


def _greeting(founder_name: str | None, company_name: str) -> str:
    """Build a personalised greeting line."""
    if founder_name:
        first = founder_name.split()[0]
        return f"Hey {first},"
    return f"Hey {company_name},"


# ------------------------------------------------------------------ #
# Email drafting                                                      #
# ------------------------------------------------------------------ #

def _draft_email(
    client: anthropic.Anthropic,
    company_name: str,
    url: str,
    context_notes: str,
    founder_name: str | None,
    retries: int = 3,
) -> tuple[str, str]:
    """Generate a (subject, body) cold outreach email using enriched context.

    Falls back to a hardcoded template if LLM call fails after all retries.
    """
    enriched = _parse_enriched_context(context_notes)
    tagline  = enriched["tagline"]

    tagline_hint = (
        f"Their product tagline is: '{tagline}'. Quote or riff on it in your hook."
        if tagline else "No tagline — write a hook based on the context notes."
    )
    founder_hint = (
        f"Address them by first name: {founder_name.split()[0]}."
        if founder_name else "No founder name — address as the team."
    )

    prompt = (
        f"Write a cold outreach email to '{company_name}' ({url}) proposing a 1-to-1 audience swap "
        f"(newsletter cross-promotion or widget placement). No financial compensation, ever.\n\n"
        f"Context about them: {context_notes}\n\n"
        f"{tagline_hint}\n"
        f"{founder_hint}\n\n"
        f"Rules:\n"
        f"- Subject: casual, specific, under 60 chars, no emojis\n"
        f"- Body: exactly 3 sentences\n"
        f"  Sentence 1 — personalised hook referencing something specific about their product\n"
        f"  Sentence 2 — shared audience and mutual benefit of the swap\n"
        f"  Sentence 3 — casual CTA, e.g. 'Open to a quick audience swap?'\n"
        f"- Do NOT include a greeting line — it will be prepended separately\n"
        f"- Do NOT include a sign-off — it will be appended separately\n\n"
        f'Respond ONLY with JSON: {{"subject": "...", "body": "..."}}'
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=Config.SMART_MODEL,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())
            subject = data.get("subject") or f"Partnership idea: Symbiote AI x {company_name}"
            body    = data.get("body") or ""
            if subject and body:
                return subject, body

        except json.JSONDecodeError:
            return _fallback_email(company_name, url)

        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            wait = 2 ** attempt
            log.warning(
                f"Anthropic API error (attempt {attempt + 1}/{retries}): {e}. "
                f"Retrying in {wait}s."
            )
            time.sleep(wait)

    log.warning(f"All retries exhausted for '{company_name}'. Using fallback.")
    return _fallback_email(company_name, url)


def _fallback_email(company_name: str, url: str) -> tuple[str, str]:
    subject = f"Quick audience swap idea — {company_name}?"
    body = (
        f"Loved what you're building at {url} and think our audiences overlap. "
        f"We're Symbiote AI, and we'd love to explore a 1-to-1 newsletter cross-promotion — "
        f"pure exposure swap, nothing more. Open to a quick audience swap?"
    )
    return subject, body


# ------------------------------------------------------------------ #
# Email assembly (plain text + HTML)                                  #
# ------------------------------------------------------------------ #

def _build_plain_text(greeting: str, body: str, contact_email: str) -> str:
    unsubscribe = f"{Config.UNSUBSCRIBE_URL}?email={url_quote(contact_email)}"
    return (
        f"{greeting}\n\n"
        f"{body}\n\n"
        f"— {Config.SENDER_NAME}\n\n"
        f"---\n"
        f"To unsubscribe from future outreach: {unsubscribe}"
    )


def _build_html(greeting: str, body: str, contact_email: str) -> str:
    """Minimal HTML email with CAN-SPAM-compliant unsubscribe footer."""
    unsubscribe = f"{Config.UNSUBSCRIBE_URL}?email={url_quote(contact_email)}"
    html_body   = body.replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Georgia,serif;max-width:580px;margin:40px auto;color:#333;line-height:1.7;padding:0 16px">
  <p>{greeting}</p>
  <p>{html_body}</p>
  <p>— {Config.SENDER_NAME}</p>
  <hr style="border:none;border-top:1px solid #eee;margin:40px 0">
  <p style="font-size:11px;color:#aaa;line-height:1.5">
    You're receiving this as a potential partnership match for Symbiote AI.<br>
    <a href="{unsubscribe}" style="color:#aaa">Unsubscribe</a>
  </p>
</body>
</html>"""


# ------------------------------------------------------------------ #
# Main                                                                #
# ------------------------------------------------------------------ #

def draft_and_send_emails(dry_run: bool | None = None) -> int:
    """Draft and send outreach emails to all qualifying scouted leads.

    Qualifying criteria:
      - status = 'scouted'
      - score  >= MIN_LEAD_SCORE  (set MIN_LEAD_SCORE=0 to disable)
      - contact_email IS NOT NULL
      - opted_out_at  IS NULL

    Args:
        dry_run: When True, emails are logged but not delivered. Defaults to Config.DRY_RUN.

    Returns:
        Number of leads successfully pitched.
    """
    if dry_run is None:
        dry_run = Config.DRY_RUN

    Config.validate("ANTHROPIC_API_KEY")
    if not dry_run:
        Config.validate("RESEND_API_KEY")
        resend.api_key = Config.RESEND_API_KEY

    if dry_run:
        log.info("DRY RUN mode — emails drafted and logged but NOT delivered.")
    else:
        log.info("LIVE mode — emails will be sent via Resend.")

    claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, company_name, url, contact_email, context_notes, score, founder_name
        FROM companies
        WHERE status        = 'scouted'
          AND opted_out_at  IS NULL
          AND contact_email IS NOT NULL
          AND score         >= ?
    """, (Config.MIN_LEAD_SCORE,))
    leads = cursor.fetchall()

    if not leads:
        log.info(
            f"No qualifying leads "
            f"(score >= {Config.MIN_LEAD_SCORE}, has email, not opted out). "
            f"Run 'symbiote enrich' first."
        )
        conn.close()
        return 0

    log.info(f"Processing {len(leads)} qualifying lead(s) (min score: {Config.MIN_LEAD_SCORE}).")
    pitched = 0

    for lead in leads:
        lead_id       = lead["id"]
        company_name  = lead["company_name"]
        url           = lead["url"]
        contact_email = lead["contact_email"]
        context_notes = lead["context_notes"] or ""
        score         = lead["score"]
        founder_name  = lead["founder_name"]

        log.info(f"Drafting for '{company_name}' [score:{score}] → {contact_email}")

        subject, body = _draft_email(
            claude, company_name, url, context_notes, founder_name
        )
        greeting  = _greeting(founder_name, company_name)
        full_text = _build_plain_text(greeting, body, contact_email)
        full_html = _build_html(greeting, body, contact_email)

        log.info(f"  Subject:  {subject}")
        log.debug(f"  Greeting: {greeting}")
        log.debug(f"  Body:     {body}")

        if not dry_run:
            try:
                resend.Emails.send({
                    "from":    f"{Config.SENDER_NAME} <{Config.SENDER_EMAIL}>",
                    "to":      [contact_email],
                    "subject": subject,
                    "text":    full_text,
                    "html":    full_html,
                })
                log.info(f"  Sent to {contact_email}.")
            except Exception as e:
                log.error(f"  Resend failed for {contact_email}: {e}")
                continue
        else:
            log.info(f"  [DRY RUN] Would send to {contact_email}.")

        cursor.execute("""
            UPDATE companies
            SET status        = 'pitched',
                email_subject = ?,
                email_body    = ?,
                pitched_at    = datetime('now'),
                updated_at    = datetime('now')
            WHERE id = ?
        """, (subject, body, lead_id))
        conn.commit()
        pitched += 1
        log.info(f"  Marked '{company_name}' as 'pitched'.")

        if pitched < len(leads):
            time.sleep(Config.EMAIL_RATE_LIMIT_SECONDS)

    conn.close()
    log.info(f"Negotiation complete. {pitched} lead(s) pitched.")
    return pitched


if __name__ == "__main__":
    draft_and_send_emails()
