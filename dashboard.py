import os
import time
import html
import requests
from typing import List, Optional
from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

from config import settings
from database import (
    init_db, get_all_leads, get_lead_by_id, update_lead_status, 
    remove_lead, log_email_sent, migrate_from_json, add_lead as db_add_lead
)

# --- Rate Limiter ---
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        # Clean up old requests
        self.requests[ip] = [req_time for req_time in self.requests.get(ip, []) if now - req_time < self.window_seconds]
        if len(self.requests[ip]) >= self.max_requests:
            return False
        self.requests[ip].append(now)
        return True

send_limiter = RateLimiter(max_requests=5, window_seconds=60)

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    init_db()
    json_path = 'lead_store.json'
    if os.path.exists(json_path):
        print(f"Migrating leads from {json_path}...")
        migrate_from_json(json_path)
    print("Dashboard Startup Complete.")
    yield
    print("Dashboard Shutdown Complete.")

# --- App Init ---
app = FastAPI(lifespan=lifespan)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5050", "http://127.0.0.1:5050"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth Middleware ---
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Only protect API routes, except health
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if settings.DASHBOARD_AUTH_TOKEN:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
            token = auth_header.split("Bearer ")[1]
            if token != settings.DASHBOARD_AUTH_TOKEN:
                return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
    
    response = await call_next(request)
    return response

# --- Pydantic Models ---
class LeadIdRequest(BaseModel):
    id: str
    pitch: Optional[str] = None

class AddLeadRequest(BaseModel):
    id: str
    company_name: str
    domain: str
    location: str
    founder_name: str
    founder_title: str
    email: str
    tech_summary: str
    pitch: str

# --- Helpers ---
def escape_lead(lead: dict) -> dict:
    return {k: (html.escape(str(v)) if isinstance(v, str) else v) for k, v in lead.items()}

# --- Routes ---
@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/leads")
def get_leads():
    try:
        leads = get_all_leads()
        return [escape_lead(lead) for lead in leads]
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/send-lead")
def send_lead(req: LeadIdRequest, request: Request):
    try:
        client_ip = request.client.host
        if not send_limiter.is_allowed(client_ip):
            return JSONResponse({"success": False, "error": "Rate limit exceeded (5 sends/min)"}, status_code=429)

        lead = get_lead_by_id(req.id)
        if not lead:
            return JSONResponse({"success": False, "error": "Lead not found"}, status_code=404)
        
        # Use provided pitch if edited, else original
        pitch_text = req.pitch if req.pitch else lead['pitch']
        
        html_content = f"""
        <div style="font-family: sans-serif; color: #333;">
            <p>{pitch_text.replace(chr(10), '<br>')}</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 11px; color: #999;">
                You received this email because we thought our services might be relevant to your business.
                <br><a href="#unsubscribe" style="color: #999;">Unsubscribe</a> | {settings.BUSINESS_ADDRESS}
            </p>
        </div>
        """

        # Send via Resend API
        res = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [lead['email']],
                "subject": f"Partnership with {lead['company_name']}",
                "html": html_content
            },
            timeout=10
        )
        
        if res.status_code in (200, 201):
            res_data = res.json()
            log_email_sent(req.id, res_data.get('id', 'unknown'))
            update_lead_status(req.id, 'SENT')
            
            # Also update pitch if it was edited
            if req.pitch and req.pitch != lead['pitch']:
                # Update pitch via db connection (add a direct sqlite execution since there's no helper)
                from database import get_connection, _lock
                with _lock:
                    with get_connection() as conn:
                        conn.execute("UPDATE leads SET pitch = ? WHERE id = ?", (req.pitch, req.id))
                        conn.commit()

            return {"success": True}
        else:
            return JSONResponse({"success": False, "error": f"Resend API error: {res.text}"}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/remove-lead")
def remove_lead_endpoint(req: LeadIdRequest):
    try:
        remove_lead(req.id)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/add-lead")
def add_lead_endpoint(req: AddLeadRequest):
    try:
        db_add_lead(req.dict())
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/")
def serve_dashboard():
    needs_auth = "true" if settings.DASHBOARD_AUTH_TOKEN else "false"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Lead CRM Agent</title>
    <style>
        :root {{
            --bg-color: #0b1120;
            --card-bg: #111827;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-color: #3b82f6;
            --success-color: #10b981;
            --danger-color: #ef4444;
            --border-color: #1f2937;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 30px;
        }}
        .title-group h1 {{
            margin: 0 0 8px 0;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .title-group p {{
            margin: 0;
            color: var(--text-secondary);
        }}
        .status-badge {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .status-badge.connected {{
            background: rgba(16, 185, 129, 0.1);
            color: var(--success-color);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}
        .status-badge.disconnected {{
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger-color);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .stat-item {{
            background: var(--card-bg);
            padding: 15px 25px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: var(--accent-color);
        }}
        .stat-label {{
            font-size: 12px;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}
        .leads-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }}
        .lead-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .lead-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }}
        .company-name {{ font-size: 18px; font-weight: 700; margin: 0; }}
        .location-tag {{
            background: #243144;
            color: #94a3b8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }}
        .founder-info {{ color: var(--text-secondary); font-size: 14px; margin-bottom: 14px; }}
        .pitch-box {{
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
            border: 1px solid transparent;
        }}
        .pitch-box[contenteditable="true"] {{
            border: 1px dashed var(--border-color);
            outline: none;
        }}
        .pitch-box[contenteditable="true"]:focus {{
            border-color: var(--accent-color);
        }}
        .btn-group {{
            display: flex;
            gap: 10px;
        }}
        .btn {{
            flex: 1;
            padding: 10px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: opacity 0.2s;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }}
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .btn-send {{ background: var(--success-color); color: white; }}
        .btn-remove {{ background: #263346; color: var(--danger-color); }}
        .btn:not(:disabled):hover {{ opacity: 0.85; }}
        .status-sent {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-color);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            font-weight: 700;
            font-size: 13px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        /* Modal & Toasts */
        #auth-modal {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }}
        .modal-content {{
            background: var(--card-bg);
            padding: 30px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            text-align: center;
        }}
        .modal-content input {{
            width: 100%;
            padding: 10px;
            margin: 15px 0;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background: #090d16;
            color: white;
            box-sizing: border-box;
        }}
        .toast-container {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 9999;
        }}
        .toast {{
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            font-size: 14px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            animation: slideIn 0.3s ease-out;
        }}
        .toast.success {{ background-color: var(--success-color); }}
        .toast.error {{ background-color: var(--danger-color); }}
        @keyframes slideIn {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}
        
        /* Spinner */
        .spinner {{
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div id="auth-modal" style="display: none;">
        <div class="modal-content">
            <h2>Authentication Required</h2>
            <p style="color: var(--text-secondary)">Please enter your dashboard token</p>
            <input type="password" id="auth-token" placeholder="Enter Token..." />
            <button class="btn btn-send" onclick="saveToken()">Login</button>
        </div>
    </div>

    <div class="toast-container" id="toast-container"></div>

    <div class="container">
        <header>
            <div class="title-group">
                <h1>Human-in-the-Loop AI Lead & Outreach Dashboard</h1>
                <p>Review captured ICP founders & approve AI personalized pitches</p>
            </div>
            <div class="status-badge" id="resend-status">
                Checking Resend...
            </div>
        </header>

        <div class="stats">
            <div class="stat-item">
                <div class="stat-value" id="stat-total">0</div>
                <div class="stat-label">Total Leads</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="stat-sent">0</div>
                <div class="stat-label">Emails Sent</div>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="font-size: 18px; margin: 0;">Captured Real ICP Founders (Review & Send)</h2>
            <button class="btn" style="background: var(--accent-color); color: white; width: auto; padding: 10px 20px;" onclick="fetchLeads()">Refresh Leads</button>
        </div>

        <div class="leads-grid" id="leads-container">
            <!-- Dynamic Lead Cards inserted via JS -->
        </div>
    </div>

    <script>
        const NEEDS_AUTH = {needs_auth};
        let authToken = localStorage.getItem('dashboard_token') || '';
        const hasResend = "{settings.RESEND_API_KEY}" !== "None" && "{settings.RESEND_API_KEY}" !== "";

        document.getElementById('resend-status').className = hasResend ? 'status-badge connected' : 'status-badge disconnected';
        document.getElementById('resend-status').textContent = hasResend ? 'LIVE PRODUCTION • RESEND CONNECTED' : 'RESEND NOT CONFIGURED';

        function showToast(message, type = 'success') {{
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${{type}}`;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => {{
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s';
                setTimeout(() => toast.remove(), 300);
            }}, 3000);
        }}

        function checkAuth() {{
            if (NEEDS_AUTH && !authToken) {{
                document.getElementById('auth-modal').style.display = 'flex';
                return false;
            }}
            return true;
        }}

        function saveToken() {{
            authToken = document.getElementById('auth-token').value;
            localStorage.setItem('dashboard_token', authToken);
            document.getElementById('auth-modal').style.display = 'none';
            fetchLeads();
        }}

        function getHeaders() {{
            const headers = {{ 'Content-Type': 'application/json' }};
            if (authToken) headers['Authorization'] = `Bearer ${{authToken}}`;
            return headers;
        }}

        async function fetchLeads() {{
            if (!checkAuth()) return;
            
            try {{
                const res = await fetch('/api/leads', {{ headers: getHeaders() }});
                if (res.status === 401 || res.status === 403) {{
                    localStorage.removeItem('dashboard_token');
                    authToken = '';
                    checkAuth();
                    return;
                }}
                
                const leads = await res.json();
                
                if(!Array.isArray(leads)) {{
                    showToast(leads.error || 'Failed to fetch leads', 'error');
                    return;
                }}

                document.getElementById('stat-total').textContent = leads.length;
                document.getElementById('stat-sent').textContent = leads.filter(l => l.status === 'SENT').length;

                const container = document.getElementById('leads-container');
                container.innerHTML = '';

                leads.forEach(lead => {{
                    const card = document.createElement('div');
                    card.className = 'lead-card';
                    
                    const topDiv = document.createElement('div');
                    
                    const headerDiv = document.createElement('div');
                    headerDiv.className = 'lead-header';
                    const compName = document.createElement('h3');
                    compName.className = 'company-name';
                    compName.textContent = lead.company_name;
                    const locTag = document.createElement('span');
                    locTag.className = 'location-tag';
                    locTag.textContent = lead.location;
                    headerDiv.appendChild(compName);
                    headerDiv.appendChild(locTag);
                    
                    const founderInfo = document.createElement('div');
                    founderInfo.className = 'founder-info';
                    const fName = document.createElement('strong');
                    fName.textContent = lead.founder_name;
                    founderInfo.appendChild(fName);
                    founderInfo.appendChild(document.createTextNode(` (${{lead.founder_title}})`));
                    founderInfo.appendChild(document.createElement('br'));
                    founderInfo.appendChild(document.createTextNode(`Domain: ${{lead.domain}} | Target: ${{lead.email}}`));
                    
                    const pitchBox = document.createElement('div');
                    pitchBox.className = 'pitch-box';
                    pitchBox.id = `pitch-${{lead.id}}`;
                    pitchBox.textContent = lead.pitch;
                    
                    topDiv.appendChild(headerDiv);
                    topDiv.appendChild(founderInfo);
                    topDiv.appendChild(pitchBox);
                    card.appendChild(topDiv);

                    if (lead.status === 'SENT') {{
                        const statusSent = document.createElement('div');
                        statusSent.className = 'status-sent';
                        statusSent.textContent = '✉ REAL EMAIL SENT VIA RESEND';
                        card.appendChild(statusSent);
                    }} else {{
                        pitchBox.setAttribute('contenteditable', 'true');
                        pitchBox.title = "Click to edit pitch before sending";
                        
                        const actionArea = document.createElement('div');
                        actionArea.className = 'btn-group';
                        
                        const sendBtn = document.createElement('button');
                        sendBtn.className = 'btn btn-send';
                        sendBtn.innerHTML = '✉ Send Email Now';
                        sendBtn.onclick = () => sendEmail(lead.id, sendBtn);
                        
                        const rmBtn = document.createElement('button');
                        rmBtn.className = 'btn btn-remove';
                        rmBtn.innerHTML = '🗑 Remove';
                        rmBtn.onclick = () => removeLead(lead.id, rmBtn);
                        
                        actionArea.appendChild(sendBtn);
                        actionArea.appendChild(rmBtn);
                        card.appendChild(actionArea);
                    }}
                    
                    container.appendChild(card);
                }});
            }} catch (err) {{
                showToast('Network error loading leads', 'error');
            }}
        }}

        async function sendEmail(leadId, btnElement) {{
            if(btnElement.disabled) return;
            if(!confirm('Send this personalized cold email now?')) return;
            
            const originalHtml = btnElement.innerHTML;
            btnElement.disabled = true;
            btnElement.innerHTML = '<div class="spinner"></div> Sending...';
            
            const editedPitch = document.getElementById(`pitch-${{leadId}}`).textContent;

            try {{
                const res = await fetch('/api/send-lead', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ id: leadId, pitch: editedPitch }})
                }});
                const data = await res.json();
                
                if(data.success) {{
                    showToast('Real Email Dispatched Successfully via Resend API!');
                    fetchLeads();
                }} else {{
                    showToast(data.error || 'Error sending email', 'error');
                    btnElement.disabled = false;
                    btnElement.innerHTML = originalHtml;
                }}
            }} catch (err) {{
                showToast('Network error sending email', 'error');
                btnElement.disabled = false;
                btnElement.innerHTML = originalHtml;
            }}
        }}

        async function removeLead(leadId, btnElement) {{
            if(btnElement.disabled) return;
            if(!confirm('Are you sure you want to remove this lead?')) return;
            
            btnElement.disabled = true;
            try {{
                const res = await fetch('/api/remove-lead', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ id: leadId }})
                }});
                const data = await res.json();
                if(data.success) {{
                    showToast('Lead removed');
                    fetchLeads();
                }} else {{
                    showToast(data.error || 'Error removing lead', 'error');
                    btnElement.disabled = false;
                }}
            }} catch (err) {{
                showToast('Network error removing lead', 'error');
                btnElement.disabled = false;
            }}
        }}

        if(checkAuth()) fetchLeads();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

if __name__ == '__main__':
    uvicorn.run("dashboard:app", host="0.0.0.0", port=5050, reload=False)
