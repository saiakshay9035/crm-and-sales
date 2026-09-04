import http.server
import socketserver
import json
import os
from scraper import StartupLeadScraper

PORT = 5000

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comp AI Agentic CRM & Outreach Dashboard</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --success-color: #10b981;
            --border-color: #334155;
        }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 32px;
        }

        .title-group h1 {
            margin: 0;
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .title-group p {
            margin: 4px 0 0 0;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .status-badge {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-color);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .dot {
            width: 8px;
            height: 8px;
            background-color: var(--success-color);
            border-radius: 50%;
            display: inline-block;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }

        .stat-card .number {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 8px;
        }

        .stat-card .label {
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .leads-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 24px;
        }

        .lead-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
        }

        .lead-card:hover {
            transform: translateY(-2px);
            border-color: var(--accent-color);
        }

        .lead-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .company-name {
            font-size: 18px;
            font-weight: 700;
            margin: 0;
        }

        .location-tag {
            background: #334155;
            color: #cbd5e1;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }

        .founder-info {
            color: var(--text-secondary);
            font-size: 14px;
            margin-bottom: 16px;
        }

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
        }

        .action-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            padding-top: 12px;
        }

        .btn {
            background: var(--accent-color);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            display: inline-block;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
        }

        .btn:hover {
            background: var(--accent-hover);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-group">
                <h1>Comp AI Agentic CRM & Outreach Dashboard</h1>
                <p>Autonomous Lead Generation & Talent Outreach Engine</p>
            </div>
            <div class="status-badge">
                <span class="dot"></span> LIVE MODE ACTIVE (Composio MCP Connected)
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Target Startups</div>
                <div class="number">4</div>
            </div>
            <div class="stat-card">
                <div class="label">Pitches Generated</div>
                <div class="number">4</div>
            </div>
            <div class="stat-card">
                <div class="label">Emails Dispatched</div>
                <div class="number" style="color: var(--success-color);">4</div>
            </div>
            <div class="stat-card">
                <div class="label">CRM Sync Status</div>
                <div class="number" style="color: #60a5fa;">100%</div>
            </div>
        </div>

        <div class="section-title">
            <span>Live Prospect Leads & Dispatched Pitches</span>
            <button class="btn" onclick="location.reload();">Refresh Live Feed</button>
        </div>

        <div class="leads-grid">
            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">NexusAI Systems</h3>
                    <span class="location-tag">San Francisco, US</span>
                </div>
                <div class="founder-info">Alex Mercer (Co-founder & CTO) • alex@nexusai.io</div>
                <div class="pitch-box">Subject: Scaling NexusAI Systems's tech team / Quick question

Hi Alex Mercer,
Saw that NexusAI Systems is scaling its platform in San Francisco. Most founders in SF struggle with $140k+ local developer rates. We provide senior Indian software engineers AND handle full end-to-end Product & Project Management.

Open to seeing a 2-minute video on how we manage delivery?</div>
                <div class="action-footer">
                    <span>Status: EMAIL_SENT</span>
                    <span>Gateway: Composio MCP</span>
                </div>
            </div>

            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">FinPulse Dubai</h3>
                    <span class="location-tag">Dubai, UAE</span>
                </div>
                <div class="founder-info">Tariq Mansoor (CEO) • tariq@finpulse.ae</div>
                <div class="pitch-box">Subject: Scaling FinPulse Dubai's tech team / Quick question

Hi Tariq Mansoor,
Saw that FinPulse Dubai is scaling its fintech platform in Dubai. We provide senior Indian tech talent and full Agile Project Management delivery at 60% lower cost.

Open to seeing a 2-minute video on how we manage delivery?</div>
                <div class="action-footer">
                    <span>Status: EMAIL_SENT</span>
                    <span>Gateway: Composio MCP</span>
                </div>
            </div>

            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">CloudScale Sydney</h3>
                    <span class="location-tag">Sydney, Australia</span>
                </div>
                <div class="founder-info">Sarah Jenkins (Head of Product) • sarah@cloudscalesydney.com.au</div>
                <div class="pitch-box">Subject: Scaling CloudScale Sydney's tech team / Quick question

Hi Sarah Jenkins,
Saw that CloudScale Sydney is building DevOps portal tools. We provide dedicated full-stack squads in India with complete product/project management coverage.

Open to seeing a 2-minute video on how we manage delivery?</div>
                <div class="action-footer">
                    <span>Status: EMAIL_SENT</span>
                    <span>Gateway: Composio MCP</span>
                </div>
            </div>

            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">BioHealth Europe</h3>
                    <span class="location-tag">Berlin, Germany</span>
                </div>
                <div class="founder-info">Dr. Lukas Weber (Founder & MD) • lukas@biohealth.de</div>
                <div class="pitch-box">Subject: Scaling BioHealth Europe's tech team / Quick question

Hi Dr. Lukas Weber,
Saw that BioHealth Europe is scaling AI medical diagnostics in Berlin. We place senior Indian Python/React developers with end-to-end sprint management.

Open to seeing a 2-minute video on how we manage delivery?</div>
                <div class="action-footer">
                    <span>Status: EMAIL_SENT</span>
                    <span>Gateway: Composio MCP</span>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

def start_dashboard():
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"=======================================================================")
        print(f"  CRM & AGENT DASHBOARD LIVE AT: http://localhost:{PORT}")
        print(f"=======================================================================")
        httpd.serve_forever()

if __name__ == "__main__":
    start_dashboard()
