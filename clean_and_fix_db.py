import sqlite3
import re
from scraper import EXCLUDED_LOCATION_KEYWORDS, is_excluded_location

conn = sqlite3.connect('leads.db')
c = conn.cursor()

c.execute("SELECT id, company_name, founder_name, domain, location, tech_summary, linkedin_url FROM leads")
rows = c.fetchall()

purged_count = 0
updated_li_count = 0

KNOWN_DIRECT_LINKEDINS = {
    "steven tey": "https://www.linkedin.com/in/steventey",
    "peer richelsen": "https://www.linkedin.com/in/peer-richelsen-5a9b9a174",
    "james hughes": "https://www.linkedin.com/in/james-hughes-trigger",
    "daniel campion": "https://www.linkedin.com/in/daniel-campion",
    "adrian del bosque": "https://www.linkedin.com/in/adrian-del-bosque",
    "scott wu": "https://www.linkedin.com/in/scott-wu-0b44551b3",
    "brendan foody": "https://www.linkedin.com/in/brendan-foody",
    "emil sitar": "https://www.linkedin.com/in/emilsitar",
    "tony holdstock-brown": "https://www.linkedin.com/in/tonyhb",
    "pontus abrahamsson": "https://www.linkedin.com/in/pontusab",
    "aleks dekic": "https://www.linkedin.com/in/aleks-dekic",
    "james hawkins": "https://www.linkedin.com/in/james-hawkins-9892901a",
    "paul copplestone": "https://www.linkedin.com/in/paulcopplestone",
    "mudassir sheikha": "https://ae.linkedin.com/in/mudassirsheikha",
    "cameron adams": "https://www.linkedin.com/in/cameronadams",
    "zach kamran": "https://www.linkedin.com/in/zach-kamran"
}

for lid, cn, fn, dom, loc, tech, lurl in rows:
    # 1. Purge Indian / Domestic leads
    if is_excluded_location(loc, tech, fn, cn, dom):
        c.execute("DELETE FROM leads WHERE id = ?", (lid,))
        purged_count += 1
        print(f"[PURGED INDIAN/DOMESTIC LEAD] {cn} ({fn})")
        continue

    # 2. Fix LinkedIn URLs: Purge search fallbacks, insert direct /in/ URLs
    clean_fn = (fn or "").strip().lower()
    new_li = lurl

    if clean_fn in KNOWN_DIRECT_LINKEDINS:
        new_li = KNOWN_DIRECT_LINKEDINS[clean_fn]
    elif lurl and "linkedin.com/search/" in lurl:
        new_li = None  # Remove search result fallback

    if new_li != lurl:
        c.execute("UPDATE leads SET linkedin_url = ? WHERE id = ?", (new_li, lid))
        updated_li_count += 1

conn.commit()
print(f"\nDatabase Fix Completed: Purged {purged_count} Indian/Domestic leads. Updated {updated_li_count} LinkedIn profile URLs.")
conn.close()
