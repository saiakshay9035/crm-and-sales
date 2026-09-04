import os
import sqlite3
import tempfile

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set default environment variables for all tests."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("RESEND_API_KEY", "test_resend_key")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "test_token")
    monkeypatch.setenv("BUSINESS_ADDRESS", "123 Test St")
    monkeypatch.setenv("CRM_API_KEY", "test_crm_key")

@pytest.fixture
def temp_db(monkeypatch):
    """Provide a temporary SQLite database for tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    monkeypatch.setenv("DB_PATH", path)
    
    # Init schema
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                company_name TEXT,
                founder_name TEXT,
                email TEXT,
                status TEXT,
                resend_id TEXT
            )
        ''')
        conn.commit()
    
    yield path
    
    os.close(fd)
    os.remove(path)

@pytest.fixture
def sample_lead_data():
    return {
        "id": "123",
        "company_name": "Acme Corp",
        "founder_name": "Jane Doe",
        "email": "jane@acme.com",
        "status": "new"
    }
