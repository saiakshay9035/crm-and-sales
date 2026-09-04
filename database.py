import sqlite3
import json
import os
import threading

DB_PATH = 'leads.db'
_lock = threading.Lock()

def get_connection():
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
                    status TEXT DEFAULT 'DRAFT_REVIEW',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
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
    with _lock:
        with get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO leads (
                    id, company_name, domain, location, founder_name, founder_title, email, tech_summary, pitch, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                lead_data.get('status', 'DRAFT_REVIEW')
            ))
            conn.commit()

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
