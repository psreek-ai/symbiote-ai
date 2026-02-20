"""CLI entry point for Symbiote AI.

Usage examples:
    python src/cli.py scout --profile "solo SaaS founders"
    python src/cli.py negotiate --dry-run
    python src/cli.py negotiate --send
    python src/cli.py verify
    python src/cli.py status
    python src/cli.py pipeline --profile "indie makers" --send
"""

import sys
import os

# Ensure src/ is on the path when invoked directly
sys.path.insert(0, os.path.dirname(__file__))

import click
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()


@click.group()
def cli():
    """Symbiote AI — Autonomous Partnership Development System.

    \b
    Stages:
      1. scout      — discover micro-SaaS companies via web search
      2. negotiate  — draft and deliver personalized partnership pitches
      3. verify     — confirm partner sites have placed the Symbiote link/widget

    Run 'symbiote <command> --help' for per-command options.
    """


# ------------------------------------------------------------------ #
# scout                                                               #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--profile", "-p",
    default="targeting indie makers and solo developers",
    show_default=True,
    help="Natural-language description of the target audience / company type.",
)
@click.option(
    "--max-results", "-n",
    default=None,
    type=int,
    help="Max Tavily results per search query (default: SCOUT_MAX_RESULTS env var).",
)
def scout(profile: str, max_results: int | None):
    """Discover new partnership leads via web search."""
    from db import init_db
    from scout import scout_leads
    init_db()
    count = scout_leads(profile, max_results=max_results)
    click.echo(f"\nDone. {count} new lead(s) added to the pipeline.")


# ------------------------------------------------------------------ #
# negotiate                                                           #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--dry-run/--send",
    default=True,
    help=(
        "--dry-run (default): draft and log emails without delivering them. "
        "--send: actually deliver via Resend (requires RESEND_API_KEY and DRY_RUN=false)."
    ),
)
def negotiate(dry_run: bool):
    """Draft and send partnership outreach emails to scouted leads."""
    from db import init_db
    from negotiate import draft_and_send_emails
    init_db()
    count = draft_and_send_emails(dry_run=dry_run)
    mode = "drafted (dry run — not sent)" if dry_run else "sent"
    click.echo(f"\nDone. {count} email(s) {mode}.")


# ------------------------------------------------------------------ #
# verify                                                              #
# ------------------------------------------------------------------ #

@cli.command()
def verify():
    """Check partner sites for Symbiote AI link or widget placement."""
    from db import init_db
    from verify import verify_placements
    init_db()
    verified, checked = verify_placements()
    click.echo(f"\nDone. {verified}/{checked} partner(s) confirmed live.")


# ------------------------------------------------------------------ #
# status                                                              #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--status-filter", "-s",
    default=None,
    help="Filter by status (scouted, pitched, negotiating, live, declined).",
)
def status(status_filter: str | None):
    """Show the current state of the partnership pipeline."""
    from db import get_connection, get_pipeline_stats, init_db
    init_db()

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            company_name,
            url,
            contact_email,
            status,
            follow_up_count,
            created_at,
            pitched_at,
            verified_at
        FROM companies
        {where}
        ORDER BY
            CASE status
                WHEN 'live'         THEN 1
                WHEN 'negotiating'  THEN 2
                WHEN 'pitched'      THEN 3
                WHEN 'scouted'      THEN 4
                WHEN 'declined'     THEN 5
            END,
            created_at DESC
    """

    if status_filter:
        cursor.execute(query.format(where="WHERE status = ?"), (status_filter,))
    else:
        cursor.execute(query.format(where=""))

    rows = cursor.fetchall()

    stats = get_pipeline_stats(cursor)
    conn.close()

    if not rows:
        click.echo("No leads found. Run 'symbiote scout' to get started.")
        return

    table = [
        [
            r["company_name"][:32],
            r["status"],
            (r["contact_email"] or "—")[:30],
            (r["pitched_at"] or "—")[:16],
            (r["verified_at"] or "—")[:16],
        ]
        for r in rows
    ]
    headers = ["Company", "Status", "Email", "Pitched At", "Verified At"]
    click.echo(tabulate(table, headers=headers, tablefmt="rounded_outline"))

    # Summary counts
    click.echo("")
    summary = [(s, stats.get(s, 0)) for s in ("live", "negotiating", "pitched", "scouted", "declined")]
    click.echo(tabulate(summary, headers=["Status", "Count"], tablefmt="simple"))


# ------------------------------------------------------------------ #
# pipeline                                                            #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--profile", "-p",
    default="targeting indie makers and solo developers",
    show_default=True,
    help="Audience profile passed to the Scout stage.",
)
@click.option(
    "--dry-run/--send",
    default=True,
    help="Passed through to the Negotiate stage.",
)
def pipeline(profile: str, dry_run: bool):
    """Run the full Scout → Negotiate → Verify pipeline in one command."""
    from db import init_db
    from pipeline import run_pipeline
    init_db()
    run_pipeline(profile, dry_run=dry_run)


if __name__ == "__main__":
    cli()
