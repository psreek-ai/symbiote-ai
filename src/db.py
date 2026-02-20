"""Database initialization and access layer for Symbiote AI.

Key design choices:
- WAL mode for safer concurrent reads during pipeline runs
- Row factory so callers get dict-like access (row["column"])
- insert_lead_if_new enforces URL-level deduplication
- _add_column_if_missing makes every schema change idempotent/migration-safe
- Indexes on status + pitched_at for common pipeline query patterns
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "leads.db")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with dict-like row access and WAL journaling."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize (or safely migrate) the database schema. Idempotent."""
    conn = get_connection()
    cursor = conn.cursor()

    # Base table — only created if it does not already exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name    TEXT    NOT NULL,
            url             TEXT    NOT NULL UNIQUE,
            contact_email   TEXT,
            status          TEXT    NOT NULL
                            CHECK(status IN ('scouted', 'pitched', 'negotiating', 'live', 'declined'))
                            DEFAULT 'scouted',
            context_notes   TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Additive migrations — safe to run on any existing DB version
    _add_column_if_missing(cursor, "companies", "email_subject",   "TEXT")
    _add_column_if_missing(cursor, "companies", "email_body",      "TEXT")
    _add_column_if_missing(cursor, "companies", "follow_up_count", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "companies", "pitched_at",      "TEXT")
    _add_column_if_missing(cursor, "companies", "verified_at",     "TEXT")

    # Enricher additions
    _add_column_if_missing(cursor, "companies", "score",        "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "companies", "enriched_at",  "TEXT")
    _add_column_if_missing(cursor, "companies", "founder_name", "TEXT")

    # CAN-SPAM / opt-out tracking
    _add_column_if_missing(cursor, "companies", "opted_out_at", "TEXT")

    # Indexes for common query patterns (idempotent)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_companies_status "
        "ON companies(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_companies_status_pitched "
        "ON companies(status, pitched_at)"
    )

    conn.commit()
    conn.close()


def _add_column_if_missing(cursor: sqlite3.Cursor, table: str, column: str, column_def: str) -> None:
    """Add a column to a table only when it does not already exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")


def insert_lead_if_new(
    cursor: sqlite3.Cursor,
    company_name: str,
    url: str,
    contact_email: str | None,
    context_notes: str,
) -> bool:
    """Insert a company row only when its URL has not been seen before.

    Returns True when a new row was inserted, False when it was skipped.
    """
    cursor.execute("SELECT id FROM companies WHERE url = ?", (url,))
    if cursor.fetchone():
        return False

    cursor.execute(
        """
        INSERT INTO companies (company_name, url, contact_email, status, context_notes)
        VALUES (?, ?, ?, 'scouted', ?)
        """,
        (company_name, url, contact_email, context_notes),
    )
    return True


def get_pipeline_stats(cursor: sqlite3.Cursor) -> dict[str, int]:
    """Return a count of leads per status across the entire pipeline."""
    cursor.execute("SELECT status, COUNT(*) AS n FROM companies GROUP BY status")
    return {row["status"]: row["n"] for row in cursor.fetchall()}


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
