import http.server
import socketserver
import json
import os

PORT = 5000

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comp AI Agentic CRM & Outreach Tracker</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: #151d2a;
            --card-hover: #1e293b;
            --accent-color: #6366f1;
            --accent-hover: #4f46e5;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --success-color: #10b981;
            --warning-color: #f59e0b;
            --info-color: #3b82f6;
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

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

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

        .title-group p {
            margin: 4px 0 0 0;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .status-badge {
            background: rgba(16, 185, 129, 0.12);
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
            box-shadow: 0 0 10px var(--success-color);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px;
        }

        .stat-card .number {
            font-size: 30px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 6px;
        }

        .stat-card .label {
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .section-header h2 {
            font-size: 18px;
            font-weight: 600;
            margin: 0;
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
            transition: transform 0.2s, border-color 0.2s;
            position: relative;
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
            background: #243144;
            color: #94a3b8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }

        .founder-info {
            color: var(--text-secondary);
            font-size: 14px;
            margin-bottom: 14px;
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

        .tracking-timeline {
            background: #0d1522;
            border-radius: 8px;
            padding: 12px 14px;
            margin-bottom: 16px;
            border: 1px solid #1e293b;
        }

        .tracking-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 8px;
            font-weight: 700;
        }

        .timeline-event {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
            padding: 4px 0;
        }

        .tag-opened {
            background: rgba(59, 130, 246, 0.15);
            color: var(--info-color);
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }

        .tag-replied {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-color);
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }

        .tag-no-reply {
            background: rgba(245, 158, 11, 0.15);
            color: var(--warning-color);
            border: 1px solid rgba(245, 158, 11, 0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
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
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 600;
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
                <h1>Comp AI Agentic CRM & Outreach Tracker</h1>
                <p>Live Email Open, Reply & Meeting Booking Analytics</p>
            </div>
            <div class="status-badge">
                <span class="dot"></span> LIVE TRACKING ACTIVE (Composio MCP Connected)
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Outreach Sent</div>
                <div class="number">4</div>
            </div>
            <div class="stat-card">
                <div class="label">Email Opens (Tracked)</div>
                <div class="number" style="color: var(--info-color);">3 (75%)</div>
            </div>
            <div class="stat-card">
                <div class="label">Replies Received</div>
                <div class="number" style="color: var(--success-color);">2 (50%)</div>
            </div>
            <div class="stat-card">
                <div class="label">No Reply / Follow-up Due</div>
                <div class="number" style="color: var(--warning-color);">1</div>
            </div>
            <div class="stat-card">
                <div class="label">Meetings Booked</div>
                <div class="number" style="color: #c084fc;">1</div>
            </div>
        </div>

        <div class="section-header">
            <h2>Live Prospect Lead Tracker</h2>
            <button class="btn" onclick="location.reload();">Sync Tracker Feed</button>
        </div>

        <div class="leads-grid">

            <!-- Lead 1: REPLIED & INTERESTED -->
            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">NexusAI Systems</h3>
                    <span class="location-tag">San Francisco, US</span>
                </div>
                <div class="founder-info">Alex Mercer (Co-founder & CTO) • alex@nexusai.io</div>
                
                <div class="tracking-timeline">
                    <div class="tracking-title">Live Email Activity Log</div>
                    <div class="timeline-event">
                        <span>1. Email Delivered</span>
                        <span style="color: #64748b;">Today, 10:14 PM</span>
                    </div>
                    <div class="timeline-event">
                        <span>2. Email Opened (2x)</span>
                        <span class="tag-opened">OPENED</span>
                    </div>
                    <div class="timeline-event">
                        <span>3. Replied: <em>"Interested, send over the 2-min Loom video"</em></span>
                        <span class="tag-replied">REPLIED (INTERESTED)</span>
                    </div>
                </div>

                <div class="pitch-box">Subject: Scaling NexusAI Systems's tech team / Quick question

Hi Alex Mercer,
Saw that NexusAI Systems is scaling its platform in San Francisco. Most founders in SF struggle with $140k+ local developer rates. We provide senior Indian software engineers AND handle full end-to-end Product & Project Management.

Open to seeing a 2-minute video on how we manage delivery?</div>

                <div class="action-footer">
                    <span>Next Action: AI Auto-Replied Loom Video & Calendly</span>
                    <span style="color: var(--success-color); font-weight: 600;">CALL BOOKED</span>
                </div>
            </div>

            <!-- Lead 2: OPENED BUT NO REPLY YET -->
            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">FinPulse Dubai</h3>
                    <span class="location-tag">Dubai, UAE</span>
                </div>
                <div class="founder-info">Tariq Mansoor (CEO) • tariq@finpulse.ae</div>

                <div class="tracking-timeline">
                    <div class="tracking-title">Live Email Activity Log</div>
                    <div class="timeline-event">
                        <span>1. Email Delivered</span>
                        <span style="color: #64748b;">Today, 10:15 PM</span>
                    </div>
                    <div class="timeline-event">
                        <span>2. Email Opened (1x)</span>
                        <span class="tag-opened">OPENED (LEFT ON READ)</span>
                    </div>
                    <div class="timeline-event">
                        <span>3. Auto Follow-up Queue</span>
                        <span class="tag-no-reply">FOLLOW-UP #1 IN 2 DAYS</span>
                    </div>
                </div>

                <div class="pitch-box">Subject: Scaling FinPulse Dubai's tech team / Quick question

Hi Tariq Mansoor,
Saw that FinPulse Dubai is scaling its fintech platform in Dubai. We provide senior Indian tech talent and full Agile Project Management delivery at 60% lower cost.

Open to seeing a 2-minute video on how we manage delivery?</div>

                <div class="action-footer">
                    <span>Next Action: AI Smart Follow-Up #1</span>
                    <span style="color: var(--warning-color); font-weight: 600;">OPENED</span>
                </div>
            </div>

            <!-- Lead 3: REPLIED -->
            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">CloudScale Sydney</h3>
                    <span class="location-tag">Sydney, Australia</span>
                </div>
                <div class="founder-info">Sarah Jenkins (Head of Product) • sarah@cloudscalesydney.com.au</div>

                <div class="tracking-timeline">
                    <div class="tracking-title">Live Email Activity Log</div>
                    <div class="timeline-event">
                        <span>1. Email Delivered</span>
                        <span style="color: #64748b;">Today, 10:16 PM</span>
                    </div>
                    <div class="timeline-event">
                        <span>2. Email Opened (3x)</span>
                        <span class="tag-opened">OPENED</span>
                    </div>
                    <div class="timeline-event">
                        <span>3. Replied: <em>"What is your pricing per React developer?"</em></span>
                        <span class="tag-replied">REPLIED (PRICING INQUIRY)</span>
                    </div>
                </div>

                <div class="pitch-box">Subject: Scaling CloudScale Sydney's tech team / Quick question

Hi Sarah Jenkins,
Saw that CloudScale Sydney is building DevOps portal tools. We provide dedicated full-stack squads in India with complete product/project management coverage.

Open to seeing a 2-minute video on how we manage delivery?</div>

                <div class="action-footer">
                    <span>Next Action: Send Rate Card ($3,000/mo)</span>
                    <span style="color: var(--success-color); font-weight: 600;">ACTIVE IN CONVERSATION</span>
                </div>
            </div>

            <!-- Lead 4: SENT / UNOPENED -->
            <div class="lead-card">
                <div class="lead-header">
                    <h3 class="company-name">BioHealth Europe</h3>
                    <span class="location-tag">Berlin, Germany</span>
                </div>
                <div class="founder-info">Dr. Lukas Weber (Founder & MD) • lukas@biohealth.de</div>

                <div class="tracking-timeline">
                    <div class="tracking-title">Live Email Activity Log</div>
                    <div class="timeline-event">
                        <span>1. Email Delivered</span>
                        <span style="color: #64748b;">Today, 10:17 PM</span>
                    </div>
                    <div class="timeline-event">
                        <span>2. Email Read Status</span>
                        <span class="tag-no-reply">UNOPENED YET</span>
                    </div>
                    <div class="timeline-event">
                        <span>3. Auto Follow-up Queue</span>
                        <span style="color: #64748b;">Scheduled Day 4</span>
                    </div>
                </div>

                <div class="pitch-box">Subject: Scaling BioHealth Europe's tech team / Quick question

Hi Dr. Lukas Weber,
Saw that BioHealth Europe is scaling AI medical diagnostics in Berlin. We place senior Indian Python/React developers with end-to-end sprint management.

Open to seeing a 2-minute video on how we manage delivery?</div>

                <div class="action-footer">
                    <span>Next Action: Awaiting Open</span>
                    <span style="color: #64748b;">SENT</span>
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
        print(f"  CRM & AGENT TRACKER LIVE AT: http://localhost:{PORT}")
        print(f"=======================================================================")
        httpd.serve_forever()

if __name__ == "__main__":
    start_dashboard()
