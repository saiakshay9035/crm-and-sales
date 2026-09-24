import json
import os
import shutil
import sqlite3
import threading

DB_PATH = os.environ.get('DB_PATH', 'leads.db')
_lock = threading.Lock()

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    with _lock, get_connection() as conn:
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
                    linkedin_url TEXT,
                    icp_reason TEXT,
                    icp_score INTEGER DEFAULT 85,
                    buying_triggers TEXT,
                    pain_signals TEXT,
                    domain_mx_status TEXT DEFAULT 'VALID',
                    mailbox_verification_status TEXT DEFAULT 'VERIFIED_EXTRACTED',
                    email_risk TEXT DEFAULT 'LOW',
                    email_source TEXT DEFAULT 'company_website',
                    last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sequence_step INTEGER DEFAULT 1,
                    outcome_status TEXT DEFAULT 'PENDING',
                    status TEXT DEFAULT 'DRAFT_REVIEW',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        # Migration check for existing databases
        cursor = conn.execute("PRAGMA table_info(leads)")
        columns = [row[1] for row in cursor.fetchall()]
        new_cols = {
            'deliverability_score': 'INTEGER',
            'deliverability_status': 'TEXT',
            'linkedin_url': 'TEXT',
            'icp_reason': 'TEXT',
            'icp_score': 'INTEGER DEFAULT 85',
            'buying_triggers': 'TEXT',
            'pain_signals': 'TEXT',
            'domain_mx_status': 'TEXT DEFAULT "VALID"',
            'mailbox_verification_status': 'TEXT DEFAULT "VERIFIED_EXTRACTED"',
            'email_risk': 'TEXT DEFAULT "LOW"',
            'email_source': 'TEXT DEFAULT "company_website"',
            'last_verified_at': 'TIMESTAMP',
            'sequence_step': 'INTEGER DEFAULT 1',
            'outcome_status': 'TEXT DEFAULT "PENDING"',
            'org_id': 'TEXT DEFAULT "org_default"'
        }
        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
        
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

        # --- Multi-Tenant SaaS Tables ---
        conn.execute('''
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plan_tier TEXT DEFAULT 'STARTER',
                    monthly_lead_limit INTEGER DEFAULT 500,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    role TEXT DEFAULT 'MEMBER',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(org_id) REFERENCES organizations(id)
                )
            ''')

        conn.execute('''
                CREATE TABLE IF NOT EXISTS invites (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT DEFAULT 'MEMBER',
                    token TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(org_id) REFERENCES organizations(id)
                )
            ''')

        conn.execute('''
                CREATE TABLE IF NOT EXISTS icp_profiles (
                    id TEXT PRIMARY KEY,
                    org_id TEXT DEFAULT 'org_default',
                    name TEXT NOT NULL,
                    target_type TEXT DEFAULT 'customers',
                    raw_prompt TEXT,
                    criteria_json TEXT,
                    is_active INTEGER DEFAULT 1,
                    lead_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(org_id) REFERENCES organizations(id)
                )
            ''')

        conn.execute('''
                CREATE TABLE IF NOT EXISTS connected_accounts (
                    id TEXT PRIMARY KEY,
                    org_id TEXT DEFAULT 'org_default',
                    provider TEXT NOT NULL,
                    email TEXT NOT NULL,
                    status TEXT DEFAULT 'CONNECTED',
                    daily_limit INTEGER DEFAULT 50,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(org_id) REFERENCES organizations(id)
                )
            ''')

        conn.execute('''
                CREATE TABLE IF NOT EXISTS lead_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    evidence_bullet TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(lead_id) REFERENCES leads(id)
                )
            ''')

        # Insert default organization & superadmin if missing
        conn.execute('''
                INSERT OR IGNORE INTO organizations (id, name, plan_tier)
                VALUES ('org_default', 'Primary Workspace', 'GROWTH')
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
    # Strict DB guard against generic emails, aggregator domains, and excluded domestic/Indian locations
    from scraper import AGGREGATOR_DOMAINS, GENERIC_EMAIL_PREFIXES, is_excluded_location
    
    email = (lead_data.get('email') or '').lower().strip()
    founder_name = (lead_data.get('founder_name') or '').strip()
    company_name = (lead_data.get('company_name') or '').strip()
    domain = (lead_data.get('domain') or '').lower().strip()
    location = (lead_data.get('location') or '').strip()
    summary = (lead_data.get('tech_summary') or '').strip()
    deliv_status = (lead_data.get('deliverability_status') or '').strip()
    
    if deliv_status and deliv_status.startswith('REJECTED_'):
        print(f"[DB Guard Rejected] Identity verification status '{deliv_status}' rejected for lead {domain}")
        return False
    
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

    if is_excluded_location(location, summary, founder_name, company_name):
        print(f"[DB Guard Rejected] Excluded domestic/Indian location for lead '{founder_name}' @ '{company_name}' ({location})")
        return False

    with _lock:
        with get_connection() as conn:
            cursor = conn.execute("SELECT id FROM leads WHERE (domain IS NOT NULL AND lower(domain) = ?) OR (email IS NOT NULL AND lower(email) = ?)", (domain, email))
            existing = cursor.fetchone()
            target_id = existing[0] if existing else (lead_data.get('id') or str(uuid.uuid4())[:8])

            conn.execute('''
                INSERT OR REPLACE INTO leads (
                    id, company_name, domain, location, founder_name, founder_title, email, tech_summary, pitch,
                    deliverability_score, deliverability_status, linkedin_url, icp_reason,
                    icp_score, buying_triggers, pain_signals, domain_mx_status, mailbox_verification_status,
                    email_risk, email_source, sequence_step, outcome_status, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                target_id,
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
                lead_data.get('linkedin_url'),
                lead_data.get('icp_reason'),
                lead_data.get('icp_score', 85),
                lead_data.get('buying_triggers', '[]'),
                lead_data.get('pain_signals', '[]'),
                lead_data.get('domain_mx_status', 'VALID'),
                lead_data.get('mailbox_verification_status', 'VERIFIED_EXTRACTED'),
                lead_data.get('email_risk', 'LOW'),
                lead_data.get('email_source', 'company_website'),
                lead_data.get('sequence_step', 1),
                lead_data.get('outcome_status', 'PENDING'),
                lead_data.get('status', 'DRAFT_REVIEW')
            ))
            conn.commit()
    return True

def update_lead_outcome(lead_id: str, outcome_status: str):
    with _lock, get_connection() as conn:
        conn.execute('UPDATE leads SET outcome_status = ? WHERE id = ?', (outcome_status, lead_id))
        conn.commit()


def update_lead_status(lead_id: str, status: str):
    with _lock, get_connection() as conn:
        conn.execute('UPDATE leads SET status = ? WHERE id = ?', (status, lead_id))
        conn.commit()

def remove_lead(lead_id: str):
    with _lock, get_connection() as conn:
        conn.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
        conn.commit()

def log_email_sent(lead_id: str, resend_id: str, status: str = 'SENT'):
    with _lock, get_connection() as conn:
        conn.execute('''
                INSERT INTO email_log (lead_id, status, resend_id)
                VALUES (?, ?, ?)
            ''', (lead_id, status, resend_id))
        conn.commit()

def clear_stub_leads():
    """Removes sample/fake demo leads from the database."""
    stub_domains = ['nexusai.io', 'finpulse.ae', 'cloudscalesydney.com.au', 'biohealth.de']
    with _lock, get_connection() as conn:
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
                            id, company_name, domain, location, founder_name, founder_title, email, tech_summary, pitch, linkedin_url, icp_reason, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        lead.get('linkedin_url'),
                        lead.get('icp_reason'),
                        lead.get('status', 'DRAFT_REVIEW')
                    ))
                conn.commit()
    except Exception as e:
        print(f"Error migrating from JSON: {e}")

def add_icp_profile(profile: dict) -> bool:
    import uuid
    pid = profile.get("id") or str(uuid.uuid4())[:8]
    org_id = profile.get("org_id", "org_default")
    name = profile.get("name", "Custom ICP Profile")
    target_type = profile.get("target_type", "customers")
    raw_prompt = profile.get("raw_prompt", "")
    criteria_json = json.dumps(profile.get("criteria", {}))

    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO icp_profiles (
                id, org_id, name, target_type, raw_prompt, criteria_json
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (pid, org_id, name, target_type, raw_prompt, criteria_json))
        conn.commit()
    return True

def get_icp_profiles(org_id: str = "org_default"):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM icp_profiles WHERE org_id = ? ORDER BY created_at DESC', (org_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            if r.get("criteria_json"):
                try:
                    r["criteria"] = json.loads(r["criteria_json"])
                except Exception:
                    r["criteria"] = {}
        return rows

def get_connected_accounts(org_id: str = "org_default"):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM connected_accounts WHERE org_id = ?', (org_id,))
        return [dict(row) for row in cursor.fetchall()]

# --- User Authentication & Multi-Tenant Invites ---
import hashlib
import uuid

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def create_organization(name: str, plan_tier: str = 'GROWTH') -> str:
    org_id = f"org_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO organizations (id, name, plan_tier)
            VALUES (?, ?, ?)
        ''', (org_id, name, plan_tier))
        conn.commit()
    return org_id

def create_user(email: str, password: str, name: str, org_name: str = None, role: str = 'MEMBER') -> dict:
    email_clean = email.strip().lower()
    pw_hash = _hash_password(password)
    user_id = f"usr_{str(uuid.uuid4())[:8]}"
    
    with _lock, get_connection() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
        if cursor.fetchone():
            raise ValueError("An account with this email address already exists.")

        org_id = 'org_default'
        if org_name:
            org_id = f"org_{str(uuid.uuid4())[:8]}"
            conn.execute("INSERT INTO organizations (id, name, plan_tier) VALUES (?, ?, 'GROWTH')", (org_id, org_name))
            role = 'OWNER'

        conn.execute('''
            INSERT INTO users (id, org_id, email, password_hash, name, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, org_id, email_clean, pw_hash, name, role))
        conn.commit()

    return {"user_id": user_id, "org_id": org_id, "email": email_clean, "name": name, "role": role}

def authenticate_user(email: str, password: str) -> dict:
    email_clean = email.strip().lower()
    pw_hash = _hash_password(password)
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT u.id as user_id, u.org_id, u.email, u.name, u.role, o.name as org_name, o.plan_tier
            FROM users u
            JOIN organizations o ON u.org_id = o.id
            WHERE u.email = ? AND u.password_hash = ?
        ''', (email_clean, pw_hash))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invalid email or password.")
        return dict(row)

def create_invite(org_id: str, target_email: str, role: str = 'MEMBER') -> dict:
    target_clean = target_email.strip().lower()
    invite_id = f"inv_{str(uuid.uuid4())[:8]}"
    token = f"tok_{str(uuid.uuid4())[:16]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO invites (id, org_id, email, role, token, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        ''', (invite_id, org_id, target_clean, role, token))
        conn.commit()
    return {"invite_id": invite_id, "org_id": org_id, "email": target_clean, "role": role, "token": token}

def get_invite_by_token(token: str) -> dict:
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT i.*, o.name as org_name
            FROM invites i
            JOIN organizations o ON i.org_id = o.id
            WHERE i.token = ? AND i.status = 'PENDING'
        ''', (token,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invalid or expired invitation link.")
        return dict(row)

def accept_invite(token: str, password: str, name: str) -> dict:
    inv = get_invite_by_token(token)
    user = create_user(
        email=inv["email"],
        password=password,
        name=name,
        role=inv["role"]
    )
    with _lock, get_connection() as conn:
        conn.execute("UPDATE users SET org_id = ? WHERE id = ?", (inv["org_id"], user["user_id"]))
        conn.execute("UPDATE invites SET status = 'ACCEPTED' WHERE id = ?", (inv["id"],))
        conn.commit()
    user["org_id"] = inv["org_id"]
    return user

def get_org_members(org_id: str):
    with get_connection() as conn:
        cursor = conn.execute("SELECT id, email, name, role, created_at FROM users WHERE org_id = ? ORDER BY created_at ASC", (org_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_org_invites(org_id: str):
    with get_connection() as conn:
        cursor = conn.execute("SELECT id, email, role, token, status, created_at FROM invites WHERE org_id = ? AND status = 'PENDING'", (org_id,))
        return [dict(row) for row in cursor.fetchall()]

# Initialize DB on import
init_db()


