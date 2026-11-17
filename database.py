import json
import os
import shutil
import sqlite3
import threading

DB_PATH = os.environ.get('DB_PATH', 'leads.db')
_lock = threading.RLock()

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
                    signal_type TEXT NOT NULL DEFAULT 'BUYING_TRIGGER',
                    description TEXT DEFAULT '',
                    evidence_bullet TEXT DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    evidence_extracted TEXT NOT NULL DEFAULT '',
                    date_discovered TEXT DEFAULT CURRENT_TIMESTAMP,
                    confidence_score REAL DEFAULT 1.0,
                    statement TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(lead_id) REFERENCES leads(id)
                )
            ''')

        # Run schema migration for existing lead_evidence tables
        try:
            cursor = conn.execute("PRAGMA table_info(lead_evidence)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            cols_to_add = {
                "source_url": "TEXT NOT NULL DEFAULT ''",
                "evidence_extracted": "TEXT NOT NULL DEFAULT ''",
                "date_discovered": "TEXT DEFAULT CURRENT_TIMESTAMP",
                "confidence_score": "REAL DEFAULT 1.0",
                "statement": "TEXT DEFAULT ''"
            }
            for col_name, col_def in cols_to_add.items():
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE lead_evidence ADD COLUMN {col_name} {col_def}")
        except Exception as e:
            pass

        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                lead_id TEXT NOT NULL,
                campaign_id TEXT DEFAULT 'default',
                subject TEXT,
                status TEXT DEFAULT 'ACTIVE',
                channel TEXT DEFAULT 'EMAIL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(org_id) REFERENCES organizations(id),
                FOREIGN KEY(lead_id) REFERENCES leads(id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                conversation_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                sender_email TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                subject TEXT,
                body_text TEXT NOT NULL,
                body_html TEXT,
                message_id TEXT,
                in_reply_to TEXT,
                references_header TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(org_id) REFERENCES organizations(id),
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS inbound_email_events (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                idempotency_key TEXT UNIQUE NOT NULL,
                provider TEXT NOT NULL,
                raw_payload TEXT,
                status TEXT DEFAULT 'PROCESSED',
                error_message TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS reply_classifications (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                message_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                evidence_text TEXT,
                recommended_action TEXT,
                should_pause_campaign INTEGER DEFAULT 1,
                requires_human_approval INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS campaign_sequences (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS sequence_steps (
                id TEXT PRIMARY KEY,
                sequence_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                delay_days INTEGER NOT NULL DEFAULT 3,
                template_subject TEXT NOT NULL,
                template_body TEXT NOT NULL,
                step_type TEXT DEFAULT 'EMAIL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sequence_id) REFERENCES campaign_sequences(id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS prospect_sequence_states (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                lead_id TEXT NOT NULL,
                sequence_id TEXT NOT NULL,
                current_step INTEGER DEFAULT 1,
                status TEXT DEFAULT 'ACTIVE',
                last_sent_at TIMESTAMP,
                next_step_due_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(org_id, lead_id, sequence_id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_actions (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                lead_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT,
                scheduled_for TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'PENDING',
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS qualification_records (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                lead_id TEXT NOT NULL,
                conversation_id TEXT,
                budget TEXT DEFAULT 'UNKNOWN',
                authority TEXT DEFAULT 'UNKNOWN',
                need TEXT DEFAULT 'UNKNOWN',
                timeline TEXT DEFAULT 'UNKNOWN',
                fit_score INTEGER DEFAULT 0,
                qualification_status TEXT DEFAULT 'IN_PROGRESS',
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS calendar_connections (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                provider TEXT NOT NULL,
                account_email TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                status TEXT DEFAULT 'CONNECTED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS meeting_bookings (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                lead_id TEXT NOT NULL,
                conversation_id TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                time_zone TEXT DEFAULT 'UTC',
                title TEXT NOT NULL,
                meeting_link TEXT,
                status TEXT DEFAULT 'CONFIRMED',
                explicit_prospect_agreement INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS agent_execution_events (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'org_default',
                event_type TEXT NOT NULL,
                lead_id TEXT,
                idempotency_key TEXT UNIQUE,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            lead_data['id'] = target_id

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

    # Save and validate any attached evidence records through the Anti-Hallucination Gate
    evidence_items = lead_data.get('evidence') or lead_data.get('evidence_list') or []
    if evidence_items and isinstance(evidence_items, list):
        for ev in evidence_items:
            try:
                add_lead_evidence(target_id, ev)
            except Exception as e:
                pass

    return True

def add_lead_evidence(lead_id: str, evidence) -> bool:
    """Validates and persists a verified evidence item linked to a lead."""
    from evidence_gate import default_gate, EvidenceItem
    if isinstance(evidence, dict):
        ev_dict = dict(evidence)
        ev_dict["lead_id"] = lead_id
        item = EvidenceItem.from_dict(ev_dict)
    elif hasattr(evidence, "to_dict"):
        item = evidence
        item.lead_id = lead_id
    else:
        return False

    is_valid, reason = default_gate.validate_evidence(item)
    if not is_valid:
        return False

    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO lead_evidence (
                lead_id, signal_type, description, evidence_bullet,
                source_url, evidence_extracted, date_discovered, confidence_score, statement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_id,
            item.signal_type,
            item.statement or item.signal_type,
            item.evidence_extracted,
            item.source_url,
            item.evidence_extracted,
            item.date_discovered,
            item.confidence_score,
            item.statement
        ))
        conn.commit()
    return True

def get_lead_evidence(lead_id: str) -> list:
    """Fetches all verified provenance evidence items for a given lead."""
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT id, lead_id, signal_type, description, evidence_bullet,
                   source_url, evidence_extracted, date_discovered, confidence_score, statement, created_at
            FROM lead_evidence
            WHERE lead_id = ?
            ORDER BY confidence_score DESC, date_discovered DESC
        ''', (lead_id,))
        return [dict(row) for row in cursor.fetchall()]

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

# ==========================================
# PHASE 3 & 4: CONVERSATION & AGENT HELPERS
# ==========================================

def create_or_get_conversation(org_id: str, lead_id: str, subject: str = "", campaign_id: str = "default") -> dict:
    """Finds existing conversation for a lead or creates a new one."""
    with _lock, get_connection() as conn:
        cursor = conn.execute("SELECT * FROM conversations WHERE org_id = ? AND lead_id = ? LIMIT 1", (org_id, lead_id))
        row = cursor.fetchone()
        if row:
            return dict(row)
        conv_id = f"conv_{str(uuid.uuid4())[:8]}"
        conn.execute('''
            INSERT INTO conversations (id, org_id, lead_id, campaign_id, subject, status)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE')
        ''', (conv_id, org_id, lead_id, campaign_id, subject))
        conn.commit()
        return {"id": conv_id, "org_id": org_id, "lead_id": lead_id, "campaign_id": campaign_id, "subject": subject, "status": "ACTIVE"}

def add_conversation_message(
    org_id: str,
    conversation_id: str,
    direction: str,
    sender_email: str,
    recipient_email: str,
    body_text: str,
    subject: str = "",
    body_html: str = "",
    message_id: str = None,
    in_reply_to: str = None,
    references_header: str = None
) -> dict:
    msg_id = f"msg_{str(uuid.uuid4())[:10]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO conversation_messages (
                id, org_id, conversation_id, direction, sender_email, recipient_email,
                subject, body_text, body_html, message_id, in_reply_to, references_header
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            msg_id, org_id, conversation_id, direction.upper(), sender_email.strip().lower(),
            recipient_email.strip().lower(), subject, body_text, body_html,
            message_id, in_reply_to, references_header
        ))
        conn.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,))
        conn.commit()
    return {
        "id": msg_id, "org_id": org_id, "conversation_id": conversation_id,
        "direction": direction.upper(), "sender_email": sender_email, "recipient_email": recipient_email,
        "subject": subject, "body_text": body_text
    }

def get_conversation(conversation_id: str, org_id: str = None) -> dict:
    with get_connection() as conn:
        if org_id:
            cursor = conn.execute("SELECT * FROM conversations WHERE id = ? AND org_id = ?", (conversation_id, org_id))
        else:
            cursor = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_conversation_messages(conversation_id: str, org_id: str = None) -> list:
    with get_connection() as conn:
        if org_id:
            cursor = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id = ? AND org_id = ? ORDER BY sent_at ASC", (conversation_id, org_id))
        else:
            cursor = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY sent_at ASC", (conversation_id,))
        return [dict(row) for row in cursor.fetchall()]

def list_conversations(org_id: str = "org_default") -> list:
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT c.*, l.company_name, l.founder_name, l.email as lead_email
            FROM conversations c
            JOIN leads l ON c.lead_id = l.id
            WHERE c.org_id = ?
            ORDER BY c.updated_at DESC
        ''', (org_id,))
        return [dict(row) for row in cursor.fetchall()]

def record_inbound_email_event(org_id: str, idempotency_key: str, provider: str, raw_payload: str) -> tuple:
    """Records an incoming webhook payload with strict idempotency."""
    event_id = f"inb_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        cursor = conn.execute("SELECT id FROM inbound_email_events WHERE idempotency_key = ?", (idempotency_key,))
        if cursor.fetchone():
            return False, "DUPLICATE"
        conn.execute('''
            INSERT INTO inbound_email_events (id, org_id, idempotency_key, provider, raw_payload, status)
            VALUES (?, ?, ?, ?, ?, 'PROCESSED')
        ''', (event_id, org_id, idempotency_key, provider, raw_payload))
        conn.commit()
    return True, event_id

def save_reply_classification(data: dict) -> str:
    class_id = f"class_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO reply_classifications (
                id, org_id, message_id, conversation_id, intent,
                confidence_score, evidence_text, recommended_action,
                should_pause_campaign, requires_human_approval
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            class_id,
            data.get("org_id", "org_default"),
            data["message_id"],
            data["conversation_id"],
            data["intent"].upper(),
            float(data.get("confidence_score", 1.0)),
            data.get("evidence_text", ""),
            data.get("recommended_action", ""),
            1 if data.get("should_pause_campaign", True) else 0,
            1 if data.get("requires_human_approval", True) else 0
        ))
        conn.commit()
    return class_id

def get_reply_classification(message_id: str, org_id: str = None) -> dict:
    with get_connection() as conn:
        if org_id:
            cursor = conn.execute("SELECT * FROM reply_classifications WHERE message_id = ? AND org_id = ?", (message_id, org_id))
        else:
            cursor = conn.execute("SELECT * FROM reply_classifications WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_sequence(org_id: str, name: str, steps: list) -> dict:
    seq_id = f"seq_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        conn.execute("INSERT INTO campaign_sequences (id, org_id, name) VALUES (?, ?, ?)", (seq_id, org_id, name))
        for step in steps:
            s_id = f"step_{str(uuid.uuid4())[:8]}"
            conn.execute('''
                INSERT INTO sequence_steps (id, sequence_id, step_number, delay_days, template_subject, template_body, step_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                s_id, seq_id, step["step_number"], step.get("delay_days", 3),
                step["template_subject"], step["template_body"], step.get("step_type", "EMAIL")
            ))
        conn.commit()
    return {"id": seq_id, "org_id": org_id, "name": name, "steps_count": len(steps)}

def get_sequence(sequence_id: str, org_id: str = None) -> dict:
    with get_connection() as conn:
        if org_id:
            cur = conn.execute("SELECT * FROM campaign_sequences WHERE id = ? AND org_id = ?", (sequence_id, org_id))
        else:
            cur = conn.execute("SELECT * FROM campaign_sequences WHERE id = ?", (sequence_id,))
        seq = cur.fetchone()
        if not seq:
            return None
        steps_cur = conn.execute("SELECT * FROM sequence_steps WHERE sequence_id = ? ORDER BY step_number ASC", (sequence_id,))
        result = dict(seq)
        result["steps"] = [dict(s) for s in steps_cur.fetchall()]
        return result

def enroll_prospect_in_sequence(org_id: str, lead_id: str, sequence_id: str) -> dict:
    state_id = f"state_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO prospect_sequence_states (
                id, org_id, lead_id, sequence_id, current_step, status, last_sent_at, next_step_due_at
            ) VALUES (?, ?, ?, ?, 1, 'ACTIVE', CURRENT_TIMESTAMP, NULL)
        ''', (state_id, org_id, lead_id, sequence_id))
        conn.commit()
    return {"id": state_id, "org_id": org_id, "lead_id": lead_id, "sequence_id": sequence_id, "status": "ACTIVE"}

def pause_all_sequences_for_lead(org_id: str, lead_id: str, reason: str = "PAUSED_REPLIED") -> int:
    with _lock, get_connection() as conn:
        cursor = conn.execute(
            "UPDATE prospect_sequence_states SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE org_id = ? AND lead_id = ? AND status = 'ACTIVE'",
            (reason, org_id, lead_id)
        )
        count = cursor.rowcount
        conn.commit()
        return count

def get_prospect_sequence_state(org_id: str, lead_id: str) -> list:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM prospect_sequence_states WHERE org_id = ? AND lead_id = ?", (org_id, lead_id))
        return [dict(row) for row in cursor.fetchall()]

def schedule_action(org_id: str, lead_id: str, action_type: str, payload_json: str, scheduled_for: str) -> str:
    act_id = f"act_{str(uuid.uuid4())[:8]}"
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO scheduled_actions (id, org_id, lead_id, action_type, payload_json, scheduled_for, status)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
        ''', (act_id, org_id, lead_id, action_type, payload_json, scheduled_for))
        conn.commit()
    return act_id

def get_due_scheduled_actions(now_iso: str = None) -> list:
    with get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM scheduled_actions
            WHERE status = 'PENDING' AND scheduled_for <= CURRENT_TIMESTAMP
            ORDER BY scheduled_for ASC
        ''')
        return [dict(row) for row in cursor.fetchall()]

def update_scheduled_action_status(action_id: str, status: str, retries: int = None) -> bool:
    with _lock, get_connection() as conn:
        if retries is not None:
            conn.execute("UPDATE scheduled_actions SET status = ?, retries = ? WHERE id = ?", (status, retries, action_id))
        else:
            conn.execute("UPDATE scheduled_actions SET status = ? WHERE id = ?", (status, action_id))
        conn.commit()
    return True

def save_qualification_record(record: dict) -> dict:
    qual_id = f"qual_{str(uuid.uuid4())[:8]}"
    org_id = record.get("org_id", "org_default")
    lead_id = record["lead_id"]
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO qualification_records (
                id, org_id, lead_id, conversation_id, budget, authority, need, timeline,
                fit_score, qualification_status, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            qual_id, org_id, lead_id, record.get("conversation_id"),
            record.get("budget", "UNKNOWN"), record.get("authority", "UNKNOWN"),
            record.get("need", "UNKNOWN"), record.get("timeline", "UNKNOWN"),
            record.get("fit_score", 0), record.get("qualification_status", "IN_PROGRESS"),
            record.get("summary", "")
        ))
        conn.commit()
    return {**record, "id": qual_id}

def get_qualification_record(lead_id: str, org_id: str = None) -> dict:
    with get_connection() as conn:
        if org_id:
            cursor = conn.execute("SELECT * FROM qualification_records WHERE lead_id = ? AND org_id = ? ORDER BY created_at DESC LIMIT 1", (lead_id, org_id))
        else:
            cursor = conn.execute("SELECT * FROM qualification_records WHERE lead_id = ? ORDER BY created_at DESC LIMIT 1", (lead_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_meeting_booking(booking: dict) -> dict:
    book_id = f"meet_{str(uuid.uuid4())[:8]}"
    org_id = booking.get("org_id", "org_default")
    with _lock, get_connection() as conn:
        conn.execute('''
            INSERT INTO meeting_bookings (
                id, org_id, lead_id, conversation_id, start_time, end_time, time_zone,
                title, meeting_link, status, explicit_prospect_agreement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            book_id, org_id, booking["lead_id"], booking.get("conversation_id"),
            booking["start_time"], booking["end_time"], booking.get("time_zone", "UTC"),
            booking["title"], booking.get("meeting_link", ""), booking.get("status", "CONFIRMED"),
            1 if booking.get("explicit_prospect_agreement", True) else 0
        ))
        conn.commit()
    return {**booking, "id": book_id}

def get_meeting_bookings(org_id: str = "org_default", lead_id: str = None) -> list:
    with get_connection() as conn:
        if lead_id:
            cur = conn.execute("SELECT * FROM meeting_bookings WHERE org_id = ? AND lead_id = ? ORDER BY start_time DESC", (org_id, lead_id))
        else:
            cur = conn.execute("SELECT * FROM meeting_bookings WHERE org_id = ? ORDER BY start_time DESC", (org_id,))
        return [dict(row) for row in cur.fetchall()]

def record_agent_event(org_id: str, event_type: str, lead_id: str = None, payload: dict = None, idempotency_key: str = None) -> bool:
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    payload_str = json.dumps(payload or {})
    with _lock, get_connection() as conn:
        if idempotency_key:
            cur = conn.execute("SELECT id FROM agent_execution_events WHERE idempotency_key = ?", (idempotency_key,))
            if cur.fetchone():
                return False
        conn.execute('''
            INSERT INTO agent_execution_events (id, org_id, event_type, lead_id, idempotency_key, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (event_id, org_id, event_type, lead_id, idempotency_key, payload_str))
        conn.commit()
    return True

def list_agent_events(org_id: str = "org_default", lead_id: str = None, limit: int = 50) -> list:
    with get_connection() as conn:
        if lead_id:
            cur = conn.execute("SELECT * FROM agent_execution_events WHERE org_id = ? AND lead_id = ? ORDER BY created_at DESC LIMIT ?", (org_id, lead_id, limit))
        else:
            cur = conn.execute("SELECT * FROM agent_execution_events WHERE org_id = ? ORDER BY created_at DESC LIMIT ?", (org_id, limit))
        return [dict(row) for row in cur.fetchall()]

# Initialize DB on import
init_db()


