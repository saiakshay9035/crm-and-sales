import pytest
import json
import tempfile
import os
from unittest.mock import patch
import database as db


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    """Override the database path to use a temp file for each test."""
    test_db = str(tmp_path / "test_leads.db")
    with patch.object(db, 'DB_PATH', test_db):
        db.init_db()
        yield test_db


@pytest.fixture
def sample_lead():
    return {
        "id": "test_lead_1",
        "company_name": "Acme Corp",
        "domain": "acme.com",
        "location": "San Francisco, US",
        "founder_name": "Jane Doe",
        "founder_title": "CEO",
        "email": "jane@acme.com",
        "tech_summary": "AI startup",
        "pitch": "Subject: Test Pitch\n\nHi Jane...",
        "status": "DRAFT_REVIEW",
    }


def test_init_db_creates_tables(use_temp_db):
    import sqlite3
    with sqlite3.connect(use_temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='email_log'")
        assert cursor.fetchone() is not None


def test_add_and_get_all_leads(sample_lead):
    db.add_lead(sample_lead)
    leads = db.get_all_leads()
    assert len(leads) >= 1
    found = [l for l in leads if l["id"] == "test_lead_1"]
    assert len(found) == 1
    assert found[0]["company_name"] == "Acme Corp"


def test_get_lead_by_id(sample_lead):
    db.add_lead(sample_lead)
    lead = db.get_lead_by_id("test_lead_1")
    assert lead is not None
    assert lead["company_name"] == "Acme Corp"


def test_get_lead_by_id_returns_none_for_missing():
    assert db.get_lead_by_id("nonexistent") is None


def test_update_lead_status(sample_lead):
    db.add_lead(sample_lead)
    db.update_lead_status("test_lead_1", "SENT")

    lead = db.get_lead_by_id("test_lead_1")
    assert lead["status"] == "SENT"


def test_remove_lead(sample_lead):
    db.add_lead(sample_lead)
    db.remove_lead("test_lead_1")
    assert db.get_lead_by_id("test_lead_1") is None


def test_log_email_sent(sample_lead):
    db.add_lead(sample_lead)
    # log_email_sent inserts into email_log table, not leads
    db.log_email_sent("test_lead_1", "resend_abc123")
    # Verify by querying email_log directly
    import sqlite3
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM email_log WHERE lead_id = ?", ("test_lead_1",))
        row = cursor.fetchone()
        assert row is not None


def test_migrate_from_json():
    fd, path = tempfile.mkstemp(suffix=".json")

    sample_json = [
        {
            "id": "json_lead_1",
            "company_name": "JSON Corp",
            "domain": "json.com",
            "location": "NY",
            "founder_name": "Bob",
            "founder_title": "CTO",
            "email": "bob@json.com",
            "tech_summary": "Data company",
            "pitch": "Hello Bob",
            "status": "DRAFT_REVIEW",
        }
    ]

    with open(path, "w") as f:
        json.dump(sample_json, f)

    try:
        db.migrate_from_json(path)
        leads = db.get_all_leads()
        found = [l for l in leads if l["id"] == "json_lead_1"]
        assert len(found) == 1
        assert found[0]["company_name"] == "JSON Corp"
    finally:
        os.close(fd)
        os.remove(path)
