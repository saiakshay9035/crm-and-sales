import sqlite3

conn = sqlite3.connect('leads.db')
conn.execute("UPDATE leads SET email = 'paul@supabase.com' WHERE id = 'lead_1'")
conn.execute("UPDATE leads SET email = 'james@posthog.com' WHERE id = 'lead_2'")
conn.execute("UPDATE leads SET email = 'mudassir@careem.com' WHERE id = 'lead_3'")
conn.execute("UPDATE leads SET email = 'cameron@canva.com' WHERE id = 'lead_4'")
conn.commit()
conn.close()
print("Updated initial sample lead emails to actual founder domain emails.")
