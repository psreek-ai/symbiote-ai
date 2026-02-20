"""Pipeline orchestrator: Scout → Enrich → Negotiate → Verify in sequence.

Uses Rich progress spinners so you can see exactly which stage is running.
Each stage is independently guarded — a failure in one stage is logged and
the pipeline continues to the next stage rather than crashing entirely.
"""

import sys
from dotenv import load_dotenv

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich import box

    _RICH = True
except ImportError:
    _RICH = False

from db import get_connection, get_pipeline_stats, init_db
from logger import get_logger

load_dotenv()
log = get_logger("pipeline")

_console = Console() if _RICH else None

_STATUS_ORDER = ("live", "negotiating", "pitched", "enriched", "scouted", "declined")


def _stage(label: str, fn, *args, **kwargs):
    """Run *fn* inside a Rich spinner (if available) and return its result.

    Returns the function's return value, or None on unhandled exception.
    """
    if _RICH and _console:
        with _console.status(f"[cyan]{label}…[/cyan]"):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                log.error(f"{label} failed: {e}")
                return None
    else:
        log.info(label)
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.error(f"{label} failed: {e}")
            return None


def run_pipeline(profile_description: str, dry_run: bool | None = None) -> None:
    """Execute all four pipeline stages and print a final summary.

    Stages:
        1. Scout      — discover leads via Tavily + Claude extraction
        2. Enrich     — scrape partner sites, extract emails, score leads
        3. Negotiate  — draft personalised pitches, send via Resend
        4. Verify     — confirm placements on partner websites

    Args:
        profile_description: Audience/company type used by the Scout stage.
        dry_run:             Passed through to Negotiate. None defers to Config.DRY_RUN.
    """
    from scout import scout_leads
    from enricher import enrich_leads
    from negotiate import draft_and_send_emails
    from verify import verify_placements

    init_db()

    if _RICH and _console:
        _console.rule("[bold cyan]Symbiote AI — Pipeline Run[/bold cyan]")
    else:
        log.info("─" * 60)
        log.info("Symbiote AI — Full Pipeline Run")
        log.info("─" * 60)

    # ------------------------------------------------------------------ #
    # Stage 1: Scout                                                       #
    # ------------------------------------------------------------------ #
    if _RICH and _console:
        _console.print("[bold][1/4][/bold] SCOUT", style="cyan")
    else:
        log.info("[1/4] SCOUT")

    new_leads = _stage("Scouting leads", scout_leads, profile_description)
    new_leads = new_leads or 0
    _log(f"Scout complete: {new_leads} new lead(s).")

    # ------------------------------------------------------------------ #
    # Stage 2: Enrich                                                      #
    # ------------------------------------------------------------------ #
    if _RICH and _console:
        _console.print("[bold][2/4][/bold] ENRICH", style="cyan")
    else:
        log.info("[2/4] ENRICH")

    enriched = _stage("Enriching leads", enrich_leads)
    enriched = enriched or 0
    _log(f"Enrich complete: {enriched} lead(s) enriched.")

    # ------------------------------------------------------------------ #
    # Stage 3: Negotiate                                                   #
    # ------------------------------------------------------------------ #
    if _RICH and _console:
        _console.print("[bold][3/4][/bold] NEGOTIATE", style="cyan")
    else:
        log.info("[3/4] NEGOTIATE")

    pitched = _stage("Drafting and sending emails", draft_and_send_emails, dry_run=dry_run)
    pitched = pitched or 0
    _log(f"Negotiate complete: {pitched} pitch(es).")

    # ------------------------------------------------------------------ #
    # Stage 4: Verify                                                      #
    # ------------------------------------------------------------------ #
    if _RICH and _console:
        _console.print("[bold][4/4][/bold] VERIFY", style="cyan")
    else:
        log.info("[4/4] VERIFY")

    result = _stage("Verifying partner placements", verify_placements)
    verified, checked = result if result else (0, 0)
    _log(f"Verify complete: {verified}/{checked} placement(s) confirmed.")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    conn   = get_connection()
    cursor = conn.cursor()
    stats  = get_pipeline_stats(cursor)
    conn.close()

    if _RICH and _console:
        lines = "\n".join(
            f"  [bold]{s:>12}[/bold]: {stats.get(s, 0)}" for s in _STATUS_ORDER
        )
        _console.print(
            Panel(lines, title="[bold cyan]Pipeline Summary[/bold cyan]", box=box.ROUNDED)
        )
    else:
        log.info("─" * 60)
        log.info("PIPELINE SUMMARY")
        log.info("─" * 60)
        for s in _STATUS_ORDER:
            log.info(f"  {s:>12}: {stats.get(s, 0)}")
        log.info("─" * 60)


def _log(msg: str) -> None:
    """Log to Rich console if available, else to standard logger."""
    if _RICH and _console:
        _console.print(f"  [green]✓[/green] {msg}")
    else:
        log.info(msg)


if __name__ == "__main__":
    profile = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "targeting indie makers and solo developers"
    run_pipeline(profile)
