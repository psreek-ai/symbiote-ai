"""CLI entry point for Symbiote AI.

Usage examples:
    symbiote scout      --profile "solo SaaS founders"
    symbiote enrich
    symbiote negotiate  --dry-run
    symbiote negotiate  --send
    symbiote followup   --dry-run
    symbiote verify
    symbiote status
    symbiote export     --out leads.csv
    symbiote webhook
    symbiote pipeline   --profile "indie makers" --send
"""

import sys
import os
import csv

# Ensure src/ is on the path when invoked directly
sys.path.insert(0, os.path.dirname(__file__))

import click
from dotenv import load_dotenv

load_dotenv()

# Try to import Rich; fall back gracefully if not installed
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box as rich_box

    _RICH = True
except ImportError:
    _RICH = False

_console = Console() if _RICH else None

# Status → Rich colour mapping
_STATUS_COLOUR = {
    "live":        "bold green",
    "negotiating": "bold cyan",
    "pitched":     "yellow",
    "enriched":    "magenta",
    "scouted":     "white",
    "declined":    "red",
}


def _status_styled(s: str) -> str:
    """Wrap a status string in Rich markup if Rich is available."""
    if not _RICH or not s:
        return s or "—"
    colour = _STATUS_COLOUR.get(s, "white")
    return f"[{colour}]{s}[/{colour}]"


@click.group()
def cli():
    """Symbiote AI — Autonomous Partnership Development System.

    \b
    Pipeline stages:
      1. scout      — discover micro-SaaS companies via web search
      2. enrich     — scrape sites, find emails, score each lead
      3. negotiate  — draft and deliver personalized partnership pitches
      4. verify     — confirm partner sites have placed the Symbiote link/widget

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
    help="Max Tavily results per query (default: SCOUT_MAX_RESULTS env var).",
)
def scout(profile: str, max_results: int | None):
    """Discover new partnership leads via web search."""
    from db import init_db
    from scout import scout_leads
    init_db()
    count = scout_leads(profile, max_results=max_results)
    click.echo(f"\nDone. {count} new lead(s) added to the pipeline.")


# ------------------------------------------------------------------ #
# enrich                                                              #
# ------------------------------------------------------------------ #

@cli.command()
def enrich():
    """Scrape partner sites, extract contact emails, and score each lead."""
    from db import init_db
    from enricher import enrich_leads
    init_db()
    count = enrich_leads()
    click.echo(f"\nDone. {count} lead(s) enriched.")


# ------------------------------------------------------------------ #
# negotiate                                                           #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--dry-run/--send",
    default=True,
    help=(
        "--dry-run (default): draft and log emails without delivering them. "
        "--send: actually deliver via Resend (requires RESEND_API_KEY)."
    ),
)
def negotiate(dry_run: bool):
    """Draft and send partnership outreach emails to enriched leads."""
    from db import init_db
    from negotiate import draft_and_send_emails
    init_db()
    count = draft_and_send_emails(dry_run=dry_run)
    mode = "drafted (dry run — not sent)" if dry_run else "sent"
    click.echo(f"\nDone. {count} email(s) {mode}.")


# ------------------------------------------------------------------ #
# followup                                                            #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--dry-run/--send",
    default=True,
    help="--dry-run: draft and log without delivering. --send: deliver via Resend.",
)
def followup(dry_run: bool):
    """Send follow-up nudges to pitched leads that haven't replied."""
    from db import init_db
    from followup import send_followups
    init_db()
    count = send_followups(dry_run=dry_run)
    mode = "drafted (dry run — not sent)" if dry_run else "sent"
    click.echo(f"\nDone. {count} follow-up(s) {mode}.")


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
    help="Filter rows by status (scouted, enriched, pitched, negotiating, live, declined).",
)
def status(status_filter: str | None):
    """Show the current state of the partnership pipeline as a table."""
    from db import get_connection, get_pipeline_stats, init_db
    init_db()

    conn   = get_connection()
    cursor = conn.cursor()

    _where = "WHERE status = ?" if status_filter else ""
    _params = (status_filter,) if status_filter else ()
    cursor.execute(f"""
        SELECT
            company_name,
            url,
            contact_email,
            status,
            score,
            follow_up_count,
            created_at,
            pitched_at,
            verified_at
        FROM companies
        {_where}
        ORDER BY
            CASE status
                WHEN 'live'         THEN 1
                WHEN 'negotiating'  THEN 2
                WHEN 'pitched'      THEN 3
                WHEN 'enriched'     THEN 4
                WHEN 'scouted'      THEN 5
                WHEN 'declined'     THEN 6
            END,
            created_at DESC
    """, _params)
    rows   = cursor.fetchall()
    stats  = get_pipeline_stats(cursor)
    conn.close()

    if not rows:
        click.echo("No leads found. Run 'symbiote scout' to get started.")
        return

    if _RICH and _console:
        tbl = Table(
            box=rich_box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            expand=False,
        )
        tbl.add_column("Company",    max_width=30, no_wrap=True)
        tbl.add_column("Status",     style="bold",  max_width=12)
        tbl.add_column("Score",      justify="right", max_width=6)
        tbl.add_column("Email",      max_width=28, no_wrap=True)
        tbl.add_column("Pitched",    max_width=16, no_wrap=True)
        tbl.add_column("Verified",   max_width=16, no_wrap=True)

        for r in rows:
            tbl.add_row(
                (r["company_name"] or "")[:30],
                _status_styled(r["status"]),
                str(r["score"] or 0),
                (r["contact_email"] or "—")[:28],
                (r["pitched_at"]  or "—")[:16],
                (r["verified_at"] or "—")[:16],
            )
        _console.print(tbl)

        # Summary row counts
        _console.print()
        summary_tbl = Table(box=rich_box.SIMPLE, show_header=True, header_style="bold")
        summary_tbl.add_column("Status")
        summary_tbl.add_column("Count", justify="right")
        for s in ("live", "negotiating", "pitched", "enriched", "scouted", "declined"):
            summary_tbl.add_row(_status_styled(s), str(stats.get(s, 0)))
        _console.print(summary_tbl)
    else:
        from tabulate import tabulate
        table = [
            [
                (r["company_name"] or "")[:32],
                r["status"],
                r["score"] or 0,
                (r["contact_email"] or "—")[:30],
                (r["pitched_at"]  or "—")[:16],
                (r["verified_at"] or "—")[:16],
            ]
            for r in rows
        ]
        headers = ["Company", "Status", "Score", "Email", "Pitched At", "Verified At"]
        click.echo(tabulate(table, headers=headers, tablefmt="rounded_outline"))
        click.echo("")
        summary = [(s, stats.get(s, 0)) for s in ("live", "negotiating", "pitched", "enriched", "scouted", "declined")]
        click.echo(tabulate(summary, headers=["Status", "Count"], tablefmt="simple"))


# ------------------------------------------------------------------ #
# export                                                              #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--out", "-o",
    default="leads_export.csv",
    show_default=True,
    help="Output CSV file path.",
)
@click.option(
    "--status-filter", "-s",
    default=None,
    help="Export only rows with this status.",
)
def export(out: str, status_filter: str | None):
    """Export all leads (or a status subset) to a CSV file."""
    from db import get_connection, init_db
    init_db()

    conn   = get_connection()
    cursor = conn.cursor()
    _where = "WHERE status = ?" if status_filter else ""
    _params = (status_filter,) if status_filter else ()
    cursor.execute(f"""
        SELECT id, company_name, url, contact_email, status, score,
               follow_up_count, context_notes, email_subject,
               created_at, pitched_at, verified_at, opted_out_at
        FROM companies
        {_where}
        ORDER BY created_at DESC
    """, _params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        click.echo("No leads to export.")
        return

    fieldnames = [
        "id", "company_name", "url", "contact_email", "status", "score",
        "follow_up_count", "context_notes", "email_subject",
        "created_at", "pitched_at", "verified_at", "opted_out_at",
    ]
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})

    click.echo(f"Exported {len(rows)} lead(s) to {out}.")


# ------------------------------------------------------------------ #
# webhook                                                             #
# ------------------------------------------------------------------ #

@cli.command()
@click.option(
    "--port", "-p",
    default=None,
    type=int,
    help="Port to listen on (default: WEBHOOK_PORT env var, fallback 8080).",
)
def webhook(port: int | None):
    """Start the inbound email webhook and unsubscribe server."""
    from config import Config
    from webhook import create_app
    _port = port or Config.WEBHOOK_PORT
    click.echo(f"Starting webhook server on port {_port}…")
    click.echo(f"  POST /webhook/inbound  — inbound email handler")
    click.echo(f"  GET  /unsubscribe      — CAN-SPAM unsubscribe endpoint")
    click.echo(f"  GET  /health           — liveness probe")
    app = create_app()
    app.run(host="0.0.0.0", port=_port)


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
    """Run the full Scout → Enrich → Negotiate → Verify pipeline in one command."""
    from db import init_db
    from pipeline import run_pipeline
    init_db()
    run_pipeline(profile, dry_run=dry_run)


if __name__ == "__main__":
    cli()
