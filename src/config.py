"""Centralized configuration for Symbiote AI.

All tuneable parameters live here. Override any value by setting the
corresponding environment variable in your .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ------------------------------------------------------------------ #
    # API keys                                                             #
    # ------------------------------------------------------------------ #
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    TAVILY_API_KEY: str = os.environ.get("TAVILY_API_KEY", "")
    RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")

    # ------------------------------------------------------------------ #
    # Sender identity (must match a verified Resend domain)               #
    # ------------------------------------------------------------------ #
    SENDER_EMAIL: str = os.environ.get("SENDER_EMAIL", "partnerships@symbiote.ai")
    SENDER_NAME: str = os.environ.get("SENDER_NAME", "Head of Partnerships, Symbiote AI")

    # ------------------------------------------------------------------ #
    # Verification: the domain we look for on partner sites               #
    # ------------------------------------------------------------------ #
    SYMBIOTE_DOMAIN: str = os.environ.get("SYMBIOTE_DOMAIN", "symbiote.ai")

    # ------------------------------------------------------------------ #
    # Scout settings                                                       #
    # ------------------------------------------------------------------ #
    SCOUT_MAX_RESULTS: int = int(os.environ.get("SCOUT_MAX_RESULTS", "5"))

    # ------------------------------------------------------------------ #
    # Negotiate settings                                                   #
    # ------------------------------------------------------------------ #
    # Seconds to wait between each outbound email (rate limiting)
    EMAIL_RATE_LIMIT_SECONDS: float = float(os.environ.get("EMAIL_RATE_LIMIT_SECONDS", "2.0"))

    # When True, emails are drafted and logged but never delivered.
    # Always start in dry-run mode; flip to false only when ready to go live.
    DRY_RUN: bool = os.environ.get("DRY_RUN", "true").lower() == "true"

    # ------------------------------------------------------------------ #
    # Enricher settings                                                    #
    # ------------------------------------------------------------------ #
    # Leads scoring below this threshold are skipped by Negotiate
    MIN_LEAD_SCORE: int = int(os.environ.get("MIN_LEAD_SCORE", "40"))

    # ------------------------------------------------------------------ #
    # Follow-up settings                                                   #
    # ------------------------------------------------------------------ #
    # Days of silence before sending follow-up #1 (and #2)
    FOLLOWUP_DELAY_DAYS: int = int(os.environ.get("FOLLOWUP_DELAY_DAYS", "5"))
    # Maximum number of follow-ups to send per lead before giving up
    FOLLOWUP_MAX_COUNT: int = int(os.environ.get("FOLLOWUP_MAX_COUNT", "2"))

    # ------------------------------------------------------------------ #
    # Webhook / CAN-SPAM                                                   #
    # ------------------------------------------------------------------ #
    WEBHOOK_PORT: int = int(os.environ.get("WEBHOOK_PORT", "8080"))
    # Full URL of your unsubscribe endpoint — appended with ?email=...
    # Defaults to localhost for development; set to your public URL in production
    UNSUBSCRIBE_URL: str = os.environ.get(
        "UNSUBSCRIBE_URL", "http://localhost:8080/unsubscribe"
    )

    # ------------------------------------------------------------------ #
    # Model selection                                                      #
    # ------------------------------------------------------------------ #
    # Fast/cheap model for structured data extraction (scout)
    FAST_MODEL: str = os.environ.get("FAST_MODEL", "claude-haiku-4-5")
    # High-quality model for email copy generation (negotiate)
    SMART_MODEL: str = os.environ.get("SMART_MODEL", "claude-sonnet-4-5")

    # ------------------------------------------------------------------ #
    # Validation helpers                                                   #
    # ------------------------------------------------------------------ #
    @classmethod
    def validate(cls, *required_keys: str) -> None:
        """Raise ValueError listing every missing environment variable."""
        missing = [k for k in required_keys if not getattr(cls, k, "")]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example to .env and fill in the values."
            )
