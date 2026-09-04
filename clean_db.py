import sqlite3

from scraper import (
    AGGREGATOR_DOMAINS,
    GENERIC_EMAIL_PREFIXES,
)

conn = sqlite3.connect('leads.db')
cursor = conn.cursor()

cursor.execute("SELECT id, company_name, founder_name, email, domain FROM leads")
rows = cursor.fetchall()

deleted_count = 0
kept_count = 0

for lead_id, company_name, founder_name, email, domain in rows:
    should_delete = False
    
    # 1. Generic email prefix check
    local_part = email.split("@")[0].lower() if email and "@" in email else ""
    if local_part in GENERIC_EMAIL_PREFIXES:
        should_delete = True
        
    # 2. Generic founder name check
    if not founder_name or founder_name.strip() in ["Founder", "Email Contacts", "Founder & CEO", "Admin", "Support"] or len(founder_name.split()) < 2:
        should_delete = True
        
    # 3. Aggregator domain check
    domain_clean = (domain or "").lower()
    email_clean = (email or "").lower()
    if any(agg in domain_clean for agg in AGGREGATOR_DOMAINS) or any(agg in email_clean for agg in AGGREGATOR_DOMAINS):
        should_delete = True
        
    if should_delete:
        cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        deleted_count += 1
        print(f"[PURGED] Deleted Lead: {lead_id}")
    else:
        kept_count += 1
        print(f"[KEPT] Valid Lead: {lead_id} | {company_name.encode('ascii', 'ignore').decode()}")

conn.commit()
print(f"\nDB Cleanup finished. Deleted: {deleted_count}, Kept: {kept_count}")
conn.close()


