import sqlite3
import json
import os
import threading

import shutil

is_serverless = bool(os.environ.get('NETLIFY') or os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or os.environ.get('LAMBDA_TASK_ROOT'))
DB_PATH = '/tmp/leads.db' if is_serverless else os.environ.get('DB_PATH', 'leads.db')
_lock = threading.Lock()

def get_connection():
    if is_serverless and not os.path.exists('/tmp/leads.db'):
        root_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leads.db')
        if os.path.exists(root_db):
            try:
                shutil.copy(root_db, '/tmp/leads.db')
            except Exception as e:
                print(f"Could not copy seed DB to /tmp: {e}")

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        with get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    company_name TEXT,
                    domain TEXT,
                    location TEXT,
                    founder_name TEXT,
                    founder_title TEXT,
                    email TEXT,
                    tech_summary TEXT,
                    pitch TEXT,
                    deliverability_score INTEGER,
                    deliverability_status TEXT,
                    status TEXT DEFAULT 'DRAFT_REVIEW',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Migration check for existing databases
            cursor = conn.execute("PRAGMA table_info(leads)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'deliverability_score' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN deliverability_score INTEGER")
            if 'deliverability_status' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN deliverability_status TEXT")
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS email_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    resend_id TEXT,
                    FOREIGN KEY(lead_id) REFERENCES leads(id)
                )
            ''')
            conn.commit()

def get_all_leads():
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM leads ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]

def get_lead_by_id(lead_id: str):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def add_lead(lead_data: dict):
    # Strict DB guard against generic emails and aggregator domains
    from scraper import GENERIC_EMAIL_PREFIXES, AGGREGATOR_DOMAINS
    
    email = (lead_data.get('email') or '').lower().strip()
    founder_name = (lead_data.get('founder_name') or '').strip()
    domain = (lead_data.get('domain') or '').lower().strip()
    
    local_part = email.split("@")[0] if "@" in email else ""
    if local_part in GENERIC_EMAIL_PREFIXES:
        print(f"[DB Guard Rejected] Generic email prefix '{local_part}@' for lead {domain}")
        return False
        
    if not founder_name or founder_name in ["Founder", "Email Contacts", "Founder & CEO", "Admin", "Support"] or len(founder_name.split()) < 2:
        print(f"[DB Guard Rejected] Generic founder name '{founder_name}' for lead {domain}")
        return False
        
    if any(agg in domain for agg in AGGREGATOR_DOMAINS) or any(agg in email for agg in AGGREGATOR_DOMAINS):
        print(f"[DB Guard Rejected] Aggregator domain '{domain}' / '{email}'")
        return False

    with _lock:
        with get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO leads (
                    id, company_name, domain, location, founder_name, founder_title, email, tech_summary, pitch, deliverability_score, deliverability_status, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead_data.get('id'),
                lead_data.get('company_name'),
                lead_data.get('domain'),
                lead_data.get('location'),
                lead_data.get('founder_name'),
                lead_data.get('founder_title'),
                lead_data.get('email'),
                lead_data.get('tech_summary'),
                lead_data.get('pitch'),
                lead_data.get('deliverability_score'),
                lead_data.get('deliverability_status'),
                lead_data.get('status', 'DRAFT_REVIEW')
            ))
            conn.commit()
    return True


def update_lead_status(lead_id: str, status: str):
    with _lock:
        with get_connection() as conn:
            conn.execute('UPDATE leads SET status = ? WHERE id = ?', (status, lead_id))
            conn.commit()

def remove_lead(lead_id: str):
    with _lock:
        with get_connection() as conn:
            conn.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
            conn.commit()

def log_email_sent(lead_id: str, resend_id: str, status: str = 'SENT'):
    with _lock:
        with get_connection() as conn:
            conn.execute('''
                INSERT INTO email_log (lead_id, status, resend_id)
                VALUES (?, ?, ?)
            ''', (lead_id, status, resend_id))
            conn.commit()

def clear_stub_leads():
    """Removes sample/fake demo leads from the database."""
    stub_domains = ['nexusai.io', 'finpulse.ae', 'cloudscalesydney.com.au', 'biohealth.de']
    with _lock:
        with get_connection() as conn:
            for domain in stub_domains:
                conn.execute('DELETE FROM leads WHERE domain = ?', (domain,))
            conn.commit()

def migrate_from_json(json_path: str):
    if not os.path.exists(json_path):
        return
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            leads = json.load(f)
            
        with _lock:
            with get_connection() as conn:
                for lead in leads:
                    conn.execute('''
                        INSERT OR IGNORE INTO leads (
                            id, company_name, domain, location, founder_name, founder_title, email, tech_summary, pitch, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        lead.get('id'),
                        lead.get('company_name'),
                        lead.get('domain'),
                        lead.get('location'),
                        lead.get('founder_name'),
                        lead.get('founder_title'),
                        lead.get('email'),
                        lead.get('tech_summary'),
                        lead.get('pitch'),
                        lead.get('status', 'DRAFT_REVIEW')
                    ))
                conn.commit()
    except Exception as e:
        print(f"Error migrating from JSON: {e}")

# Initialize DB on import
init_db()
