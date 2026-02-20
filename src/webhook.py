"""Webhook server: handles inbound email replies and CAN-SPAM unsubscribe requests.

Endpoints:
  POST /webhook/inbound  — Resend inbound email payload; classifies reply intent
                           with Claude and updates lead status accordingly
  GET  /unsubscribe      — CAN-SPAM unsubscribe link target; marks lead as declined
  GET  /health           — liveness probe

Setup:
  1. Configure Resend inbound routing to POST to POST /webhook/inbound
     https://resend.com/docs/send/inbound-emails
  2. Set UNSUBSCRIBE_URL=https://your-domain.com/unsubscribe in .env
  3. Run:  python src/webhook.py
     or add to a process manager (systemd, supervisor, etc.)

Intent classification:
  positive  → status: negotiating  (they're interested)
  negative  → status: declined     (they said no)
  ooo       → no status change     (out-of-office auto-reply)
  unclear   → no status change     (logged for manual review)
"""

import os
import json
import anthropic
from flask import Flask, request, jsonify

from config import Config
from db import get_connection, init_db
from logger import get_logger

log = get_logger("webhook")
app = Flask(__name__)


# ------------------------------------------------------------------ #
# Intent classification                                               #
# ------------------------------------------------------------------ #

def _classify_intent(client: anthropic.Anthropic, email_body: str, company_name: str) -> str:
    """Use Claude to classify reply intent. Returns one of: positive/negative/ooo/unclear."""
    prompt = (
        f"Classify the intent of this email reply from '{company_name}'.\n\n"
        f"Reply:\n{email_body[:1500]}\n\n"
        f"Intent categories:\n"
        f"- positive: interested, open to talking, asks follow-up questions, says yes\n"
        f"- negative: declines, not interested, unsubscribes, says no\n"
        f"- ooo: automated out-of-office / vacation reply\n"
        f"- unclear: cannot determine intent from the text\n\n"
        f'Respond ONLY with JSON: {{"intent": "positive|negative|ooo|unclear", "reason": "one sentence"}}'
    )
    try:
        response = client.messages.create(
            model=Config.FAST_MODEL,
            max_tokens=128,
            system="You classify email reply intent. Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text.strip())
        return data.get("intent", "unclear")
    except Exception as e:
        log.warning(f"Intent classification failed: {e}")
        return "unclear"


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/webhook/inbound", methods=["POST"])
def inbound_email():
    """Handle an inbound email webhook from Resend."""
    payload = request.get_json(silent=True) or {}

    from_email = (payload.get("from") or "").strip().lower()
    subject    = payload.get("subject", "")
    body       = payload.get("text") or payload.get("html") or ""

    if not from_email:
        return jsonify({"error": "Missing sender email"}), 400

    log.info(f"Inbound email from: {from_email} | Subject: {subject}")

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, company_name, status FROM companies WHERE LOWER(contact_email) = ?",
        (from_email,),
    )
    lead = cursor.fetchone()

    if not lead:
        log.info(f"No lead matched {from_email} — ignoring.")
        conn.close()
        return jsonify({"status": "no_match"}), 200

    lead_id      = lead["id"]
    company_name = lead["company_name"]
    curr_status  = lead["status"]

    log.info(f"Matched to '{company_name}' (current status: {curr_status})")

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    intent = _classify_intent(client, body, company_name)
    log.info(f"Intent: {intent}")

    new_status: str | None = None
    if intent == "positive" and curr_status in ("pitched", "scouted"):
        new_status = "negotiating"
    elif intent == "negative":
        new_status = "declined"

    if new_status:
        cursor.execute("""
            UPDATE companies
            SET status        = ?,
                context_notes = context_notes || ' | Reply: ' || ?,
                updated_at    = datetime('now')
            WHERE id = ?
        """, (new_status, intent, lead_id))
        conn.commit()
        log.info(f"Updated '{company_name}': {curr_status} → {new_status}")
    else:
        log.info(f"No status change (intent: {intent})")

    conn.close()
    return jsonify({"status": "processed", "intent": intent}), 200


@app.route("/unsubscribe", methods=["GET"])
def unsubscribe():
    """CAN-SPAM unsubscribe endpoint. Marks the lead as declined and opted-out."""
    email = (request.args.get("email") or "").strip().lower()
    if not email:
        return "Missing email parameter.", 400

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, company_name FROM companies WHERE LOWER(contact_email) = ?",
        (email,),
    )
    lead = cursor.fetchone()

    if lead:
        cursor.execute("""
            UPDATE companies
            SET status       = 'declined',
                opted_out_at = datetime('now'),
                updated_at   = datetime('now')
            WHERE id = ?
        """, (lead["id"],))
        conn.commit()
        log.info(f"Unsubscribed: {email} ('{lead['company_name']}')")

    conn.close()
    return (
        "<html><body style='font-family:sans-serif;max-width:500px;margin:80px auto'>"
        "<h2>You've been unsubscribed.</h2>"
        "<p>You won't receive any further outreach from Symbiote AI.<br>"
        "If this was a mistake, reply to any of our previous emails.</p>"
        "</body></html>",
        200,
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    init_db()
    port = Config.WEBHOOK_PORT
    log.info(f"Webhook server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
