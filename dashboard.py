import http.server
import socketserver
import json
import os
import requests
from config import settings

PORT = 5050
socketserver.TCPServer.allow_reuse_address = True
STORE_FILE = "lead_store.json"

def load_leads():
    if os.path.exists(STORE_FILE):
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_leads(leads):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2)

def send_via_resend(to_email, pitch):
    lines = pitch.strip().split("\n")
    subject = "Quick question regarding tech delivery"
    body = pitch

    if lines[0].startswith("Subject:"):
        subject = lines[0].replace("Subject:", "").strip()
        body = "\n".join(lines[1:]).strip()

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        {body.replace(chr(10), '<br>')}
    </div>
    """
    
    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html_body
    }
    
    res = requests.post(url, headers=headers, json=payload, timeout=10)
    return res.status_code in [200, 201]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Human-in-the-Loop AI Lead & Outreach Dashboard</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: #151d2a;
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --success-color: #10b981;
            --danger-color: #ef4444;
            --border-color: #263346;
        }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
        }

        .container { max-width: 1280px; margin: 0 auto; }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 28px;
        }

        .title-group h1 {
            margin: 0;
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .title-group p { margin: 4px 0 0 0; color: var(--text-secondary); font-size: 14px; }

        .status-badge {
            background: rgba(16, 185, 129, 0.12);
            color: var(--success-color);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .leads-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 24px;
        }

        .lead-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .lead-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }

        .company-name { font-size: 18px; font-weight: 700; margin: 0; }

        .location-tag {
            background: #243144;
            color: #94a3b8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }

        .founder-info { color: var(--text-secondary); font-size: 14px; margin-bottom: 14px; }

        .pitch-box {
            background: #090d16;
            border-radius: 8px;
            padding: 14px;
            font-size: 13px;
            line-height: 1.5;
            color: #cbd5e1;
            border-left: 3px solid var(--accent-color);
            margin-bottom: 16px;
            white-space: pre-wrap;
            max-height: 180px;
            overflow-y: auto;
        }

        .btn-group {
            display: flex;
            gap: 10px;
        }

        .btn {
            flex: 1;
            padding: 10px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: opacity 0.2s;
        }

        .btn-send { background: var(--success-color); color: white; }
        .btn-remove { background: #263346; color: var(--danger-color); }

        .btn:hover { opacity: 0.85; }

        .status-sent {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-color);
            padding: 8px;
            border-radius: 6px;
            text-align: center;
            font-weight: 700;
            font-size: 13px;
            width: 100%;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-group">
                <h1>Human-in-the-Loop AI Lead & Outreach Dashboard</h1>
                <p>Review captured ICP founders & approve AI personalized pitches</p>
            </div>
            <div class="status-badge">
                LIVE PRODUCTION • RESEND CONNECTED
            </div>
        </header>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="font-size: 18px; margin: 0;">Captured Real ICP Founders (Review & Send)</h2>
            <button class="btn" style="background: var(--accent-color); color: white; width: auto; padding: 10px 20px;" onclick="location.reload();">Refresh Leads</button>
        </div>

        <div class="leads-grid" id="leads-container">
            <!-- Dynamic Lead Cards inserted via JS -->
        </div>
    </div>

    <script>
        async function fetchLeads() {
            const res = await fetch('/api/leads');
            const leads = await res.json();
            const container = document.getElementById('leads-container');
            container.innerHTML = '';

            leads.forEach(lead => {
                const card = document.createElement('div');
                card.className = 'lead-card';
                
                let actionArea = `
                    <div class="btn-group">
                        <button class="btn btn-send" onclick="sendEmail('${lead.id}')">🚀 Send Email Now</button>
                        <button class="btn btn-remove" onclick="removeLead('${lead.id}')">❌ Remove</button>
                    </div>
                `;

                if (lead.status === 'SENT') {
                    actionArea = `<div class="status-sent">✅ REAL EMAIL SENT VIA RESEND</div>`;
                }

                card.innerHTML = `
                    <div>
                        <div class="lead-header">
                            <h3 class="company-name">${lead.company_name}</h3>
                            <span class="location-tag">${lead.location}</span>
                        </div>
                        <div class="founder-info"><strong>${lead.founder_name}</strong> (${lead.founder_title})<br>Domain: ${lead.domain} | Target: ${lead.email}</div>
                        <div class="pitch-box">${lead.pitch}</div>
                    </div>
                    ${actionArea}
                `;
                container.appendChild(card);
            });
        }

        async function sendEmail(leadId) {
            if(!confirm('Send this personalized cold email now?')) return;
            const res = await fetch('/api/send-lead', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ id: leadId })
            });
            const data = await res.json();
            if(data.success) {
                alert('🚀 Real Email Dispatched Successfully via Resend API!');
                fetchLeads();
            } else {
                alert('Error sending email: ' + data.error);
            }
        }

        async function removeLead(leadId) {
            const res = await fetch('/api/remove-lead', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ id: leadId })
            });
            fetchLeads();
        }

        fetchLeads();
    </script>
</body>
</html>
"""

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/leads":
            leads = load_leads()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(leads).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        leads = load_leads()
        
        if self.path == "/api/send-lead":
            lead_id = data.get("id")
            for lead in leads:
                if lead["id"] == lead_id:
                    success = send_via_resend(lead["email"], lead["pitch"])
                    if success:
                        lead["status"] = "SENT"
                        save_leads(leads)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                        return
            
            self.send_response(400)
            self.end_headers()

        elif self.path == "/api/remove-lead":
            lead_id = data.get("id")
            leads = [l for l in leads if l["id"] != lead_id]
            save_leads(leads)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

def start_dashboard():
    with socketserver.TCPServer(("", PORT), DashboardRequestHandler) as httpd:
        print(f"=======================================================================")
        print(f"  HUMAN-IN-THE-LOOP CRM DASHBOARD LIVE AT: http://localhost:{PORT}")
        print(f"=======================================================================")
        httpd.serve_forever()

if __name__ == "__main__":
    start_dashboard()
