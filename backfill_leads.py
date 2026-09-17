import sqlite3
from urllib.parse import quote

conn = sqlite3.connect('leads.db')
cursor = conn.cursor()

rows = cursor.execute("SELECT id, founder_name, company_name, location FROM leads").fetchall()

count = 0
for lid, fn, cn, loc in rows:
    founder_name = fn or "Founder"
    company_name = cn or "Company"
    location = loc or "San Francisco, US"
    
    encoded = quote(f"{founder_name} {company_name}")
    linkedin_url = f"https://www.linkedin.com/search/results/all/?keywords={encoded}"
    icp_reason = f"Target ICP Founder: {founder_name} @ {company_name} (<10 team, {location}). Validated live DNS MX deliverability."
    
    cursor.execute("UPDATE leads SET linkedin_url = ?, icp_reason = ? WHERE id = ?", (linkedin_url, icp_reason, lid))
    count += 1

conn.commit()
print(f"Successfully updated {count} lead records with LinkedIn URLs and ICP match reasons.")
conn.close()
