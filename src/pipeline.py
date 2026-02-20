"""Pipeline orchestrator: runs Scout → Negotiate → Verify in sequence.

Use this when you want a single command to drive the full BD cycle.
Each stage is independently logged and its output is summarised at the end.
"""

import sys
import os
from dotenv import load_dotenv

from db import get_connection, get_pipeline_stats, init_db
from logger import get_logger

load_dotenv()
log = get_logger("pipeline")

_DIVIDER = "─" * 60


def run_pipeline(profile_description: str, dry_run: bool | None = None) -> None:
    """Execute all three pipeline stages and print a final summary.

    Args:
        profile_description: Audience/company type used by the Scout stage.
        dry_run:             Passed through to Negotiate. None defers to Config.DRY_RUN.
    """
    from scout import scout_leads
    from negotiate import draft_and_send_emails
    from verify import verify_placements

    init_db()

    log.info(_DIVIDER)
    log.info("Symbiote AI — Full Pipeline Run")
    log.info(_DIVIDER)

    # ------------------------------------------------------------------ #
    # Stage 1: Scout                                                       #
    # ------------------------------------------------------------------ #
    log.info("[1/3] SCOUT")
    try:
        new_leads = scout_leads(profile_description)
    except Exception as e:
        log.error(f"Scout stage failed: {e}")
        new_leads = 0
    log.info(f"Scout complete: {new_leads} new lead(s).\n")

    # ------------------------------------------------------------------ #
    # Stage 2: Negotiate                                                   #
    # ------------------------------------------------------------------ #
    log.info("[2/3] NEGOTIATE")
    try:
        pitched = draft_and_send_emails(dry_run=dry_run)
    except Exception as e:
        log.error(f"Negotiate stage failed: {e}")
        pitched = 0
    log.info(f"Negotiate complete: {pitched} pitch(es).\n")

    # ------------------------------------------------------------------ #
    # Stage 3: Verify                                                      #
    # ------------------------------------------------------------------ #
    log.info("[3/3] VERIFY")
    try:
        verified, checked = verify_placements()
    except Exception as e:
        log.error(f"Verify stage failed: {e}")
        verified, checked = 0, 0
    log.info(f"Verify complete: {verified}/{checked} placement(s) confirmed.\n")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    log.info(_DIVIDER)
    log.info("PIPELINE SUMMARY")
    log.info(_DIVIDER)
    conn = get_connection()
    cursor = conn.cursor()
    stats = get_pipeline_stats(cursor)
    conn.close()

    for status_label in ("live", "negotiating", "pitched", "scouted", "declined"):
        count = stats.get(status_label, 0)
        log.info(f"  {status_label:>12}: {count}")

    log.info(_DIVIDER)


if __name__ == "__main__":
    profile = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "targeting indie makers and solo developers"
    run_pipeline(profile)
