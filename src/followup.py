"""Follow-up Module: sends timed re-engagement emails to pitched leads that haven't replied.

Pipeline position: runs independently, on a separate cron schedule from Negotiate.

Logic:
  Query leads where:
    status = 'pitched'
    AND opted_out_at IS NULL
    AND follow_up_count < FOLLOWUP_MAX_COUNT
    AND pitched_at < NOW - FOLLOWUP_DELAY_DAYS

  For each qualifying lead, draft a short follow-up (#1 or #2) and send it.
  Increment follow_up_count after every successful send.

Copy principles (mirroring the main email guardrails):
  - Follow-up #1: casual bump — assume it got buried, one sentence
  - Follow-up #2: final check-in — low-friction yes/no, closes the loop gracefully
  - Never mention money or compensation
  - Subject line always starts with "Re: " so it threads correctly
"""

import json
import time
import resend
import anthropic

from config import Config
from db import get_connection
from logger import get_logger

log = get_logger("followup")

_SYSTEM_PROMPT = (
    "You are the Head of Partnerships at Symbiote AI. "
    "You're following up on a cold email that went unanswered. "
    "Be warm, not pushy. Never mention money, compensation, or revenue. "
    "Write like a real person, not a sales bot."
)

_FALLBACK: dict[int, tuple[str, str]] = {
    1: (
        "Re: {subject}",
        "Hey — just bumping this up in case it got buried. Still think there's a "
        "great audience overlap worth exploring. Open to a quick swap?",
    ),
    2: (
        "Re: {subject}",
        "Last nudge from my end — totally understand if the timing isn't right. "
        "If it ever makes sense, I'd love to revisit. No pressure either way.",
    ),
}


def _draft_followup(
    client: anthropic.Anthropic,
    company_name: str,
    original_subject: str,
    follow_up_num: int,
    retries: int = 3,
) -> tuple[str, str]:
    """Generate a (subject, body) follow-up email. Falls back to hardcoded template."""

    tone = {
        1: "One sentence. Assume the email got buried. Casual bump.",
        2: "Two sentences max. Make it easy to say yes or no. Final outreach.",
    }.get(follow_up_num, "One sentence. Casual.")

    prompt = (
        f"Write follow-up #{follow_up_num} to '{company_name}'. "
        f"Their original email subject was: '{original_subject}'.\n\n"
        f"Tone directive: {tone}\n\n"
        f"Rules:\n"
        f"- Subject must start with 'Re: ' so it threads in their inbox\n"
        f"- No emojis, no corporate language\n"
        f"- Never mention money, compensation, or revenue share\n"
        f'Respond ONLY with JSON: {{"subject": "Re: ...", "body": "..."}}'
    )

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=Config.SMART_MODEL,
                max_tokens=256,
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
            subject = data.get("subject") or f"Re: {original_subject}"
            body    = data.get("body") or ""
            if subject and body:
                return subject, body

        except json.JSONDecodeError:
            return _make_fallback(follow_up_num, original_subject)

        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            wait = 2 ** attempt
            log.warning(f"API error (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait}s.")
            time.sleep(wait)

    return _make_fallback(follow_up_num, original_subject)


def _make_fallback(follow_up_num: int, original_subject: str) -> tuple[str, str]:
    tpl = _FALLBACK.get(follow_up_num, _FALLBACK[1])
    return tpl[0].format(subject=original_subject), tpl[1]


def send_followups(dry_run: bool | None = None) -> int:
    """Send follow-up emails to leads that have gone quiet past the configured window.

    Args:
        dry_run: When True, drafts are logged but not delivered. Defaults to Config.DRY_RUN.

    Returns:
        Number of follow-up emails sent (or drafted in dry-run mode).
    """
    if dry_run is None:
        dry_run = Config.DRY_RUN

    Config.validate("ANTHROPIC_API_KEY")
    if not dry_run:
        Config.validate("RESEND_API_KEY")
        resend.api_key = Config.RESEND_API_KEY

    if dry_run:
        log.info("DRY RUN mode — follow-ups drafted but NOT delivered.")

    claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, company_name, contact_email, email_subject, follow_up_count
        FROM companies
        WHERE status      = 'pitched'
          AND opted_out_at IS NULL
          AND contact_email IS NOT NULL
          AND follow_up_count < ?
          AND pitched_at < datetime('now', ? || ' days')
        ORDER BY pitched_at ASC
    """, (Config.FOLLOWUP_MAX_COUNT, f"-{Config.FOLLOWUP_DELAY_DAYS}"))
    leads = cursor.fetchall()

    if not leads:
        log.info(
            f"No leads due for follow-up "
            f"(>{Config.FOLLOWUP_DELAY_DAYS}d since pitch, "
            f"<{Config.FOLLOWUP_MAX_COUNT} prior follow-ups)."
        )
        conn.close()
        return 0

    log.info(f"{len(leads)} lead(s) due for follow-up.")
    sent = 0

    for lead in leads:
        lead_id          = lead["id"]
        company_name     = lead["company_name"]
        contact_email    = lead["contact_email"]
        original_subject = lead["email_subject"] or "our audience swap"
        follow_up_num    = lead["follow_up_count"] + 1

        log.info(f"Drafting follow-up #{follow_up_num} for '{company_name}' → {contact_email}")
        subject, body = _draft_followup(claude, company_name, original_subject, follow_up_num)

        log.info(f"  Subject: {subject}")
        log.debug(f"  Body: {body}")

        if not dry_run:
            try:
                resend.Emails.send({
                    "from": f"{Config.SENDER_NAME} <{Config.SENDER_EMAIL}>",
                    "to": [contact_email],
                    "subject": subject,
                    "text": body,
                })
                log.info(f"  Sent follow-up #{follow_up_num} to {contact_email}.")
            except Exception as e:
                log.error(f"  Resend failed: {e}")
                continue
        else:
            log.info(f"  [DRY RUN] Would send follow-up #{follow_up_num} to {contact_email}.")

        cursor.execute("""
            UPDATE companies
            SET follow_up_count = follow_up_count + 1,
                updated_at      = datetime('now')
            WHERE id = ?
        """, (lead_id,))
        conn.commit()
        sent += 1

        if sent < len(leads):
            time.sleep(Config.EMAIL_RATE_LIMIT_SECONDS)

    conn.close()
    log.info(f"Follow-up complete. {sent} email(s) {'drafted' if dry_run else 'sent'}.")
    return sent


if __name__ == "__main__":
    send_followups()
