"""Tests for database initialization, migrations, and helper functions."""
import sqlite3
import pytest
import db as db_module


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    """Redirect the db module to an isolated temp database for each test."""
    db_path = str(tmp_path / "test_leads.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


# ------------------------------------------------------------------ #
# init_db                                                             #
# ------------------------------------------------------------------ #

def test_init_db_creates_companies_table(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'")
    assert cur.fetchone() is not None, "companies table was not created"
    conn.close()


def test_init_db_is_idempotent(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    # Calling init_db twice must not raise
    db_module.init_db()
    db_module.init_db()


def test_init_db_adds_new_columns_to_existing_db(monkeypatch, tmp_path):
    """Simulate an old DB without the new columns; init_db should migrate it safely."""
    db_path = str(tmp_path / "old_leads.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    # Create minimal old-schema table
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            contact_email TEXT,
            status TEXT NOT NULL DEFAULT 'scouted',
            context_notes TEXT
        )
    """)
    conn.commit()
    conn.close()

    # Running init_db must add the new columns without error
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(companies)")
    columns = {row["name"] for row in cur.fetchall()}
    conn.close()

    for expected in ("email_subject", "email_body", "follow_up_count", "pitched_at", "verified_at"):
        assert expected in columns, f"Expected column '{expected}' not found after migration"


# ------------------------------------------------------------------ #
# insert_lead_if_new                                                  #
# ------------------------------------------------------------------ #

def test_insert_lead_if_new_inserts_first_time(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = db_module.get_connection()
    cur = conn.cursor()

    inserted = db_module.insert_lead_if_new(cur, "Acme", "https://acme.com", "hello@acme.com", "A test company")
    conn.commit()

    assert inserted is True
    cur.execute("SELECT COUNT(*) AS n FROM companies")
    assert cur.fetchone()["n"] == 1
    conn.close()


def test_insert_lead_if_new_deduplicates_by_url(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = db_module.get_connection()
    cur = conn.cursor()

    db_module.insert_lead_if_new(cur, "Acme", "https://acme.com", None, "First")
    conn.commit()
    inserted_again = db_module.insert_lead_if_new(cur, "Acme Renamed", "https://acme.com", None, "Dup")
    conn.commit()

    assert inserted_again is False
    cur.execute("SELECT COUNT(*) AS n FROM companies")
    assert cur.fetchone()["n"] == 1
    conn.close()


def test_insert_lead_if_new_accepts_null_email(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = db_module.get_connection()
    cur = conn.cursor()

    inserted = db_module.insert_lead_if_new(cur, "NoEmail Corp", "https://noemail.io", None, "No email here")
    conn.commit()

    assert inserted is True
    cur.execute("SELECT contact_email FROM companies WHERE url = 'https://noemail.io'")
    assert cur.fetchone()["contact_email"] is None
    conn.close()


# ------------------------------------------------------------------ #
# get_pipeline_stats                                                  #
# ------------------------------------------------------------------ #

def test_get_pipeline_stats_counts_per_status(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = db_module.get_connection()
    cur = conn.cursor()

    db_module.insert_lead_if_new(cur, "Alpha", "https://alpha.io", None, "")
    db_module.insert_lead_if_new(cur, "Beta", "https://beta.io", None, "")
    db_module.insert_lead_if_new(cur, "Gamma", "https://gamma.io", None, "")
    cur.execute("UPDATE companies SET status = 'pitched' WHERE company_name IN ('Beta', 'Gamma')")
    conn.commit()

    stats = db_module.get_pipeline_stats(cur)
    assert stats.get("scouted") == 1
    assert stats.get("pitched") == 2
    conn.close()


def test_get_pipeline_stats_empty_db(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = db_module.get_connection()
    cur = conn.cursor()
    stats = db_module.get_pipeline_stats(cur)
    assert stats == {}
    conn.close()
