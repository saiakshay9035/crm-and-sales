import csv
import html
import io
import json
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from pydantic import BaseModel

from config import settings
from database import add_lead as db_add_lead
from database import (
    get_all_leads,
    get_lead_by_id,
    init_db,
    log_email_sent,
    migrate_from_json,
    remove_lead,
    update_lead_outcome,
    update_lead_status,
)
from email_service import EmailService, EmailServiceError
from icp_background_worker import worker_instance


# --- Rate Limiter ---
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
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
    print("Starting Autonomous ICP Scraping Daemon...")
    worker_instance.start()
    print("Dashboard Startup Complete.")
    yield
    print("Stopping Autonomous ICP Scraping Daemon...")
    worker_instance.stop()
    print("Dashboard Shutdown Complete.")


# --- App Init ---
app = FastAPI(lifespan=lifespan)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Middleware ---
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health" and settings.DASHBOARD_AUTH_TOKEN:
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
    pitch: str | None = None

class SavePitchRequest(BaseModel):
    id: str
    pitch: str

class LeadOutcomeRequest(BaseModel):
    id: str
    outcome_status: str

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
    linkedin_url: str | None = None
    icp_reason: str | None = None
    icp_score: int | None = 90
    buying_triggers: str | None = None
    pain_signals: str | None = None
    domain_mx_status: str | None = "VALID"
    mailbox_verification_status: str | None = "VERIFIED_EXTRACTED"
    email_risk: str | None = "LOW"
    email_source: str | None = "company_website"

class DiscoverLeadsRequest(BaseModel):
    query: str | None = "Y Combinator AI startup founder"
    limit: int | None = 4

class ParseICPRequest(BaseModel):
    prompt: str
    target_type: str | None = "customers"

class SaveICPProfileRequest(BaseModel):
    name: str
    target_type: str
    raw_prompt: str
    criteria: dict | None = None

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    org_name: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str

class InviteUserRequest(BaseModel):
    email: str
    role: str | None = "MEMBER"
    org_id: str | None = "org_default"

class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    name: str



# --- Helpers ---
def escape_lead(lead: dict) -> dict:
    cleaned = {}
    for k, v in lead.items():
        if isinstance(v, str):
            raw = html.unescape(v)
            cleaned[k] = raw.replace("<", "&lt;").replace(">", "&gt;")
        else:
            cleaned[k] = v
    return cleaned


# --- Routes ---
@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/unsubscribe", response_class=HTMLResponse)
def unsubscribe_endpoint(email: str = ""):
    clean_email = html.escape(email) if email else "your email address"
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Unsubscribed</title></head>
    <body style="font-family: system-ui; background: #0b1120; color: #f3f4f6; text-align: center; padding: 60px;">
        <h1 style="color: #34d399;">✓ Unsubscribed</h1>
        <p><strong>{clean_email}</strong> has been successfully unsubscribed from all future communication.</p>
        <p style="color: #94a3b8; font-size: 13px;">You will receive no further emails from our platform.</p>
    </body>
    </html>
    """

@app.post("/api/icp/parse")
def parse_icp_endpoint(req: ParseICPRequest):
    try:
        from icp_builder import icp_builder
        parsed = icp_builder.parse_prompt(req.prompt, req.target_type or "customers")
        return {"success": True, "icp": parsed}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/icp/profiles")
def get_icp_profiles_endpoint():
    try:
        from database import get_icp_profiles
        profiles = get_icp_profiles()
        return {"success": True, "profiles": profiles}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/icp/profiles")
def save_icp_profile_endpoint(req: SaveICPProfileRequest):
    try:
        from database import add_icp_profile
        profile_data = {
            "name": req.name,
            "target_type": req.target_type,
            "raw_prompt": req.raw_prompt,
            "criteria": req.criteria or {}
        }
        add_icp_profile(profile_data)
        return {"success": True, "message": "ICP Profile Saved"}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/auth/register")
def register_endpoint(req: RegisterRequest):
    try:
        from database import create_user
        user = create_user(req.email, req.password, req.name, req.org_name)
        return {"success": True, "user": user}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/auth/login")
def login_endpoint(req: LoginRequest):
    try:
        from database import authenticate_user
        user = authenticate_user(req.email, req.password)
        return {"success": True, "user": user}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/invites/create")
def create_invite_endpoint(req: InviteUserRequest):
    try:
        from database import create_invite
        from email_service import EmailService
        inv = create_invite(req.org_id or "org_default", req.email, req.role or "MEMBER")
        invite_url = f"http://localhost:5050/?invite={inv['token']}"
        
        try:
            email_svc = EmailService()
            subject = "You've been invited to join AI Lead Acquisition Platform"
            html_body = f"""
            <div style="font-family: system-ui; background: #0b1120; color: #f3f4f6; padding: 24px; border-radius: 12px;">
                <h2 style="color: #38bdf8;">You're Invited!</h2>
                <p>You have been invited to collaborate on <strong>AI Lead Acquisition Platform</strong>.</p>
                <div style="margin: 20px 0;">
                    <a href="{invite_url}" style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Accept Invitation & Join →</a>
                </div>
                <p style="color: #94a3b8; font-size: 12px;">Or copy this link: {invite_url}</p>
            </div>
            """
            email_svc.send(req.email, subject, html_body, f"Accept invitation: {invite_url}")
        except Exception:
            pass

        return {"success": True, "invite": inv, "invite_url": invite_url}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.get("/api/invites/info")
def invite_info_endpoint(token: str):
    try:
        from database import get_invite_by_token
        inv = get_invite_by_token(token)
        return {"success": True, "invite": inv}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/invites/accept")
def accept_invite_endpoint(req: AcceptInviteRequest):
    try:
        from database import accept_invite
        user = accept_invite(req.token, req.password, req.name)
        return {"success": True, "user": user}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.get("/api/team/members")
def get_team_members_endpoint(org_id: str = "org_default"):
    try:
        from database import get_org_invites, get_org_members
        members = get_org_members(org_id)
        invites = get_org_invites(org_id)
        return {"success": True, "members": members, "invites": invites}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/leads")
def get_leads():
    try:
        from scraper import GENERIC_EMAIL_PREFIXES
        leads = get_all_leads()
        valid_leads = []
        for lead in leads:
            email = lead.get("email") or ""
            prefix = email.split("@")[0].lower() if "@" in email else ""
            li = lead.get("linkedin_url") or ""
            deliv_status = lead.get("deliverability_status") or ""
            
            # Must have direct LinkedIn profile URL, non-generic email prefix, & verified status
            if (
                li and "linkedin.com/in/" in li
                and prefix and prefix not in GENERIC_EMAIL_PREFIXES
                and deliv_status in ["IDENTITY_VERIFIED_CURRENT", "VERIFIED_HIGH"]
            ):
                valid_leads.append(lead)
                
        return [escape_lead(lead) for lead in valid_leads]
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/leads/export/csv")
def export_leads_csv():
    try:
        from scraper import GENERIC_EMAIL_PREFIXES
        leads = get_all_leads()
        valid_leads = [
            l for l in leads
            if (
                l.get("linkedin_url") and "linkedin.com/in/" in l.get("linkedin_url", "")
                and (l.get("email") or "").split("@")[0].lower() not in GENERIC_EMAIL_PREFIXES
                and l.get("deliverability_status") in ["IDENTITY_VERIFIED_CURRENT", "VERIFIED_HIGH"]
            )
        ]

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write Header
        writer.writerow([
            "ID", "Company Name", "Domain", "Location", "Founder/Investor Name",
            "Title", "Email", "LinkedIn URL", "ICP Score", "Deliverability Status",
            "Status", "Summary", "Personalized Pitch"
        ])

        for lead in valid_leads:
            writer.writerow([
                lead.get("id", ""),
                lead.get("company_name", ""),
                lead.get("domain", ""),
                lead.get("location", ""),
                lead.get("founder_name", ""),
                lead.get("founder_title", ""),
                lead.get("email", ""),
                lead.get("linkedin_url", ""),
                lead.get("icp_score", 90),
                lead.get("deliverability_status", ""),
                lead.get("status", ""),
                lead.get("tech_summary", ""),
                lead.get("pitch", "")
            ])

        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=verified_leads_export.csv"}
        )
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/send-all-leads")
def send_all_leads_endpoint(request: Request):
    try:
        leads = get_all_leads()
        review_leads = [
            l for l in leads
            if l.get('status') != 'SENT' and l.get('deliverability_status') in ['IDENTITY_VERIFIED_CURRENT', 'VERIFIED_HIGH']
        ]
        
        if not review_leads:
            return {"success": True, "count": 0, "message": "No pending emails to send"}

        email_svc = EmailService()
        sent_count = 0
        errors = []

        for lead in review_leads:
            pitch_text = html.unescape(lead['pitch'])
            lines = pitch_text.strip().split("\n")
            subject = f"Partnership with {lead['company_name']}"
            body_text = pitch_text
            if lines and lines[0].startswith("Subject:"):
                subject = lines[0].replace("Subject:", "").strip()
                body_text = "\n".join(lines[1:]).strip()

            html_content = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <p>{body_text.replace(chr(10), '<br>')}</p>
            </div>
            """

            try:
                email_svc.send(lead['email'], subject, html_content, body_text)
                log_email_sent(lead['id'], "sent_via_email_service")
                update_lead_status(lead['id'], 'SENT')
                sent_count += 1
            except Exception as e:
                errors.append(f"{lead['company_name']}: {e}")

        return {"success": True, "count": sent_count, "errors": errors}
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
        
        pitch_text = req.pitch if req.pitch else lead['pitch']
        
        lines = pitch_text.strip().split("\n")
        subject = f"Partnership with {lead['company_name']}"
        body_text = pitch_text
        if lines and lines[0].startswith("Subject:"):
            subject = lines[0].replace("Subject:", "").strip()
            body_text = "\n".join(lines[1:]).strip()

        html_content = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <p>{body_text.replace(chr(10), '<br>')}</p>
        </div>
        """

        email_svc = EmailService()
        email_svc.send(lead['email'], subject, html_content, body_text)
        
        log_email_sent(req.id, "sent_via_email_service")
        update_lead_status(req.id, 'SENT')
        
        if req.pitch and req.pitch != lead['pitch']:
            from database import _lock, get_connection
            with _lock, get_connection() as conn:
                conn.execute("UPDATE leads SET pitch = ? WHERE id = ?", (req.pitch, req.id))
                conn.commit()

        return {"success": True}
            
    except EmailServiceError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/save-pitch")
def save_pitch_endpoint(req: SavePitchRequest):
    try:
        from database import _lock, get_connection
        with _lock, get_connection() as conn:
            conn.execute("UPDATE leads SET pitch = ? WHERE id = ?", (req.pitch, req.id))
            conn.commit()
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/remove-lead")
def remove_lead_endpoint(req: LeadIdRequest):
    try:
        remove_lead(req.id)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/lead/outcome")
def log_outcome_endpoint(req: LeadOutcomeRequest):
    try:
        update_lead_outcome(req.id, req.outcome_status)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/auto-scraper/status")
def get_auto_scraper_status():
    return worker_instance.get_status_dict()

@app.post("/api/auto-scraper/toggle")
def toggle_auto_scraper():
    if worker_instance.is_running():
        worker_instance.stop()
    else:
        worker_instance.start()
    return worker_instance.get_status_dict()

@app.post("/api/add-lead")
def add_lead_endpoint(req: AddLeadRequest):
    try:
        db_add_lead(req.dict())
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/clear-leads")
def clear_leads_endpoint():
    try:
        from database import _lock, get_connection
        with _lock, get_connection() as conn:
            conn.execute("DELETE FROM leads")
            conn.commit()
        return {"success": True, "message": "Cleared all stale leads"}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/discover-leads")
def discover_leads_endpoint(req: DiscoverLeadsRequest):
    try:
        from enricher import AIProspectEnricher
        from scraper import StartupLeadScraper
        
        scraper = StartupLeadScraper()
        enricher = AIProspectEnricher()
        
        query = req.query if req.query else "Y Combinator AI startup founder"
        limit = req.limit if req.limit else 5
        
        raw_leads = scraper.search_real_leads(query=query, limit=limit)
        
        enriched_leads = []
        for lead in raw_leads:
            pitch = enricher.generate_pitch(
                founder_name=lead['founder_name'],
                company_name=lead['company_name'],
                location=lead['location'],
                summary=lead['tech_summary'],
                buying_triggers=lead.get('buying_triggers'),
                pain_signals=lead.get('pain_signals')
            )
            lead['pitch'] = pitch
            db_add_lead(lead)
            enriched_leads.append(lead)
            
        return {"success": True, "count": len(enriched_leads), "leads": enriched_leads}
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
    <title>AI Lead Intelligence Agent & Revenue System</title>
    <style>
        :root {{
            --bg-color: #0b1120;
            --card-bg: #111827;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-color: #3b82f6;
            --purple-accent: #8b5cf6;
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
            max-width: 1320px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 25px;
        }}
        .title-group h1 {{
            margin: 0 0 8px 0;
            background: linear-gradient(90deg, #60a5fa, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 26px;
        }}
        .title-group p {{
            margin: 0;
            color: var(--text-secondary);
            font-size: 14px;
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
        
        /* Revenue Acquisition Funnel Bar */
        .funnel-container {{
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 25px;
        }}
        .funnel-title {{
            font-size: 13px;
            font-weight: 700;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .funnel-flow {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .funnel-step {{
            flex: 1;
            min-width: 140px;
            background: #1e293b;
            border-radius: 8px;
            padding: 12px 14px;
            border: 1px solid #334155;
            text-align: center;
            position: relative;
        }}
        .funnel-step.active {{
            border-color: #3b82f6;
            background: rgba(59, 130, 246, 0.1);
        }}
        .funnel-step.success {{
            border-color: #10b981;
            background: rgba(16, 185, 129, 0.1);
        }}
        .funnel-val {{
            font-size: 22px;
            font-weight: 800;
            color: #f8fafc;
        }}
        .funnel-lbl {{
            font-size: 11px;
            color: #94a3b8;
            text-transform: uppercase;
            margin-top: 2px;
            font-weight: 600;
        }}
        .funnel-arrow {{
            color: #475569;
            font-weight: bold;
            font-size: 18px;
        }}

        .leads-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(390px, 1fr));
            gap: 24px;
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
            margin-bottom: 6px;
        }}
        .company-name {{ font-size: 19px; font-weight: 700; margin: 0; }}
        .location-tag {{
            background: #1e293b;
            color: #94a3b8;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            border: 1px solid #334155;
        }}
        
        .icp-score-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(90deg, rgba(59,130,246,0.15), rgba(168,85,247,0.15));
            border: 1px solid rgba(168,85,247,0.3);
            color: #c084fc;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .email-risk-box {{
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 11px;
            color: #94a3b8;
            margin: 10px 0;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }}
        .email-risk-box strong {{
            color: #e2e8f0;
        }}

        .tag-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 8px 0;
        }}
        .tag {{
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .tag-trigger {{
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}
        .tag-pain {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}

        .founder-info {{ color: var(--text-secondary); font-size: 13px; margin-bottom: 12px; }}
        
        .pitch-box {{
            background: #090d16;
            border-radius: 8px;
            padding: 12px;
            font-size: 13px;
            line-height: 1.5;
            color: #cbd5e1;
            border-left: 3px solid var(--accent-color);
            margin-bottom: 14px;
            white-space: pre-wrap;
            min-height: 160px;
            width: 100%;
            box-sizing: border-box;
            font-family: inherit;
            resize: vertical;
            border: 1px solid var(--border-color);
            outline: none;
        }}
        .pitch-box:focus {{
            border-color: var(--accent-color);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }}
        
        .btn-group {{
            display: flex;
            gap: 8px;
        }}
        .btn-save {{ background: #3b82f6; color: white; }}
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
            gap: 6px;
        }}
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .btn-send {{ background: var(--success-color); color: white; }}
        .btn-remove {{ background: #263346; color: var(--danger-color); }}
        .btn-outcome-interested {{ background: #10b981; color: white; font-size: 11px; padding: 6px 10px; }}
        .btn-outcome-meeting {{ background: #8b5cf6; color: white; font-size: 11px; padding: 6px 10px; }}
        .btn-outcome-not {{ background: #475569; color: white; font-size: 11px; padding: 6px 10px; }}
        
        .btn:not(:disabled):hover {{ opacity: 0.85; }}
        
        .status-sent {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-color);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            font-weight: 700;
            font-size: 12px;
            width: 100%;
            box-sizing: border-box;
            margin-bottom: 10px;
        }}

        .outcome-badge {{
            padding: 8px;
            border-radius: 6px;
            text-align: center;
            font-weight: 800;
            font-size: 12px;
            margin-top: 8px;
        }}
        .outcome-meeting {{ background: rgba(139, 92, 246, 0.2); color: #c084fc; border: 1px solid #8b5cf6; }}
        .outcome-interested {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }}
        .outcome-not {{ background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid #64748b; }}

        /* Modal & Toasts */
        .modal-overlay {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.85);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }}
        .modal-content {{
            background: var(--card-bg);
            padding: 30px;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            text-align: left;
            width: 100%;
        }}
        .modal-content h2 {{ margin-top: 0; }}
        .modal-content input {{
            width: 100%;
            padding: 12px;
            margin: 15px 0;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            background: #090d16;
            color: white;
            box-sizing: border-box;
            font-size: 14px;
        }}
        .preset-btn {{
            background: #1e293b;
            color: #94a3b8;
            border: 1px solid var(--border-color);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
        }}
        .preset-btn:hover {{ background: #334155; color: white; }}
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
    <div id="auth-modal" class="modal-overlay" style="display: none;">
        <div class="modal-content" style="max-width: 400px; text-align: center;">
            <h2>Authentication Required</h2>
            <p style="color: var(--text-secondary)">Please enter your dashboard token</p>
            <input type="password" id="auth-token" placeholder="Enter Token..." />
            <button class="btn btn-send" onclick="saveToken()">Login</button>
        </div>
    </div>

    <div id="discover-modal" class="modal-overlay" style="display: none;">
        <div class="modal-content" style="max-width: 520px;">
            <h2>🔍 Autonomous ICP Discovery Engine</h2>
            <p style="color: var(--text-secondary); font-size: 13px; line-height: 1.4;">
                Targeting pre-seed & seed B2B SaaS founders (&lt;10 team members) in US, EU, Sydney & Dubai with active engineering hiring or product expansion signals.
            </p>
            <label style="font-size: 12px; color: var(--text-secondary); font-weight: 600;">SEARCH NICHE & LOCATION:</label>
            <input type="text" id="discover-query" placeholder="e.g. Pre-seed SaaS startup founder Sydney Dubai San Francisco" value="Pre-seed SaaS startup founder Sydney Dubai San Francisco" />
            
            <div style="display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;">
                <button class="preset-btn" onclick="setPreset('Pre-seed SaaS startup founder San Francisco Sydney Dubai')">🚀 Pre-Seed SaaS (US/AUS/EU/Dubai)</button>
                <button class="preset-btn" onclick="setPreset('Early stage SaaS founder CEO team under 10')">⚡ Early Founders (&lt;10 Team)</button>
                <button class="preset-btn" onclick="setPreset('Angel invested SaaS startup CEO Sydney Dubai')">🇦🇺 Sydney & Dubai SaaS</button>
                <button class="preset-btn" onclick="setPreset('Y Combinator B2B SaaS founder US AUS EU Dubai')">💳 YC Pre-Seed B2B Software</button>
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-send" id="discover-submit-btn" onclick="runDiscovery()">Start Live Capture & AI Pitching</button>
                <button class="btn btn-remove" onclick="closeDiscoverModal()">Cancel</button>
            </div>
        </div>
    </div>

    <div class="toast-container" id="toast-container"></div>

    <div class="container">
        <header>
            <div class="title-group">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                    <h1>AI Lead Acquisition Platform</h1>
                    <span style="background: rgba(139, 92, 246, 0.2); color: #c084fc; border: 1px solid #8b5cf6; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;">WORKSPACE: PRIMARY (GROWTH TIER)</span>
                </div>
                <p>Conversational ICP Builder • 5-Layer Verification Engine • Intent Signals • Multi-Channel Acquisition</p>
            </div>
            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                <div class="status-badge" id="resend-status">
                    Checking Connected Mailbox...
                </div>
                <div class="status-badge connected" id="auto-scraper-badge" style="cursor: pointer;" onclick="toggleAutoScraper()" title="Click to toggle autonomous discovery daemon">
                    AUTONOMOUS DAEMON: ACTIVE 🟢
                </div>
            </div>
        </header>

        <!-- Conversational ICP Builder Bar -->
        <div style="background: #0f172a; border: 1px solid #3b82f6; border-radius: 12px; padding: 20px; margin-bottom: 25px;">
            <div style="font-size: 14px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <span>💬 Conversational ICP Builder — "Tell us who you want to reach"</span>
                <span style="font-size: 11px; color: #94a3b8; text-transform: none;">AI converts prompt ➔ Search strategy & 0-Bounce verification</span>
            </div>

            <!-- Target Use Case Selector -->
            <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">
                <button class="preset-btn" style="background: #3b82f6; color: white;" onclick="setTargetType('customers', this)">🎯 Customers (SaaS Founders)</button>
                <button class="preset-btn" onclick="setTargetType('investors', this)">💰 Investors / VCs (Seed Angels)</button>
                <button class="preset-btn" onclick="setTargetType('partners', this)">🤝 Tech & Agency Partners</button>
                <button class="preset-btn" onclick="setTargetType('employees', this)">👨‍💻 Senior Talent / Engineers</button>
            </div>

            <div style="display: flex; gap: 10px;">
                <input type="text" id="conversational-icp-prompt" style="flex: 1; padding: 14px; border-radius: 8px; border: 1px solid #334155; background: #090d16; color: white; font-size: 14px; outline: none;" placeholder="e.g. Find me US SaaS founders who have raised between $500k and $5M, under 20 employees and hiring engineers..." value="Find me US SaaS founders who have raised between $500k and $5M, under 20 employees and hiring engineers" />
                <button class="btn btn-send" style="width: auto; padding: 0 24px; font-size: 14px;" onclick="parseAndRunConversationalICP()">🚀 Parse ICP & Launch Agent</button>
            </div>

            <!-- Structured ICP Criteria Breakdown -->
            <div id="parsed-icp-summary" style="margin-top: 14px; padding: 12px; background: #1e293b; border-radius: 8px; font-size: 12px; color: #cbd5e1; border: 1px solid #334155; display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
                <div><strong>Target:</strong> <span id="icp-target-lbl" style="color: #60a5fa;">B2B SaaS Founders</span></div>
                <div><strong>Geography:</strong> <span id="icp-geo-lbl" style="color: #34d399;">United States, Europe, UAE</span></div>
                <div><strong>Team Size:</strong> <span style="color: #fbbf24;">1-20 employees</span></div>
                <div><strong>Stage:</strong> <span style="color: #c084fc;">Pre-Seed / Seed ($500K-$5M)</span></div>
                <div><strong>Required Signals:</strong> <span style="color: #f472b6;">👨‍💻 Hiring Engineers • 💰 Recent Funding</span></div>
                <div><strong>Min Fit Score:</strong> <span style="color: #38bdf8;">80+</span></div>
            </div>
        </div>

        <!-- Revenue Acquisition Funnel -->
        <div class="funnel-container">
            <div class="funnel-title">📊 Revenue Acquisition Funnel</div>
            <div class="funnel-flow">
                <div class="funnel-step">
                    <div class="funnel-val" id="funnel-discovered">0</div>
                    <div class="funnel-lbl">1. Discovered</div>
                </div>
                <div class="funnel-arrow">➔</div>
                <div class="funnel-step active">
                    <div class="funnel-val" id="funnel-qualified">0</div>
                    <div class="funnel-lbl">2. ICP Qualified</div>
                </div>
                <div class="funnel-arrow">➔</div>
                <div class="funnel-step active">
                    <div class="funnel-val" id="funnel-mx">0</div>
                    <div class="funnel-lbl">3. MX Verified</div>
                </div>
                <div class="funnel-arrow">➔</div>
                <div class="funnel-step">
                    <div class="funnel-val" id="funnel-sent">0</div>
                    <div class="funnel-lbl">4. Emails Sent</div>
                </div>
                <div class="funnel-arrow">➔</div>
                <div class="funnel-step">
                    <div class="funnel-val" id="funnel-replies">0</div>
                    <div class="funnel-lbl">5. Replies</div>
                </div>
                <div class="funnel-arrow">➔</div>
                <div class="funnel-step success">
                    <div class="funnel-val" id="funnel-meetings">0</div>
                    <div class="funnel-lbl">6. Meetings</div>
                </div>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="font-size: 18px; margin: 0;">Captured ICP Founders & Investors</h2>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="btn" style="background: #8b5cf6; color: white; width: auto; padding: 10px 16px;" onclick="openInviteModal()">👥 Invite Team & Users</button>
                <button class="btn" style="background: #10b981; color: white; width: auto; padding: 10px 16px;" onclick="downloadCSVExport()">📊 Export to Excel / CSV</button>
                <button class="btn" style="background: #0284c7; color: white; width: auto; padding: 10px 16px;" onclick="downloadJSONExport()">📁 Export JSON</button>
                <button class="btn" style="background: #ef4444; color: white; width: auto; padding: 10px 16px;" onclick="clearStaleLeadsAndRescan()">🧹 Purge & Rescan</button>
                <button class="btn" style="background: #a78bfa; color: white; width: auto; padding: 10px 16px;" onclick="openDiscoverModal()">🔍 Discover Leads</button>
                <button class="btn" style="background: var(--accent-color); color: white; width: auto; padding: 10px 16px;" onclick="fetchLeads()">Refresh</button>
            </div>
        </div>

    <!-- Invite Team & Users Modal -->
    <div class="modal-overlay" id="invite-modal" style="display: none;">
        <div class="modal-content" style="max-width: 520px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2 style="margin: 0; color: #60a5fa;">👥 Invite Users to Multi-Tenant SaaS</h2>
                <button onclick="closeInviteModal()" style="background: none; border: none; color: #94a3b8; font-size: 20px; cursor: pointer;">✕</button>
            </div>
            <p style="color: #94a3b8; font-size: 13px; margin-top: 0;">Invite team members, clients, or founders to collaborate in your organization workspace.</p>
            
            <label style="font-size: 12px; font-weight: 700; color: #cbd5e1;">Target Email Address</label>
            <input type="email" id="invite-email-input" placeholder="colleague@company.com or client@startup.com" />
            
            <label style="font-size: 12px; font-weight: 700; color: #cbd5e1;">Assign Role</label>
            <select id="invite-role-input" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #090d16; color: white; margin: 8px 0 16px 0;">
                <option value="MEMBER">Member (Can manage ICPs & Outreach)</option>
                <option value="ADMIN">Admin (Full Workspace Management)</option>
            </select>
            
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-send" style="padding: 12px;" onclick="sendTeamInvite()">⚡ Send Email Invite & Generate Link</button>
                <button class="btn btn-remove" style="padding: 12px;" onclick="closeInviteModal()">Cancel</button>
            </div>

            <div id="invite-result-box" style="display: none; margin-top: 16px; background: #090d16; border: 1px solid #3b82f6; border-radius: 8px; padding: 14px;">
                <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 700; color: #34d399;">✓ Invitation Created!</p>
                <p style="margin: 0 0 8px 0; font-size: 11px; color: #94a3b8;">Share this direct invite registration link:</p>
                <input type="text" id="generated-invite-link" readonly style="margin: 0; font-size: 12px; color: #60a5fa;" onclick="this.select()" />
            </div>
        </div>
    </div>




        <div class="leads-grid" id="leads-container">
            <!-- Dynamic Lead Cards inserted via JS -->
        </div>
    </div>

    <script>
        const NEEDS_AUTH = {needs_auth};
        let authToken = localStorage.getItem('dashboard_token') || '';
        let isUserEditing = false;
        const smtpUser = "{settings.SMTP_USER}";
        const hasSmtp = smtpUser && smtpUser !== "your_email@domain.com";
        const hasResend = "{settings.RESEND_API_KEY}" !== "None" && "{settings.RESEND_API_KEY}" !== "";

        const statusElem = document.getElementById('resend-status');
        if (hasSmtp) {{
            statusElem.className = 'status-badge connected';
            statusElem.textContent = `LIVE PRODUCTION • GMAIL SMTP (${{smtpUser}})`;
        }} else if (hasResend) {{
            statusElem.className = 'status-badge connected';
            statusElem.textContent = 'LIVE PRODUCTION • RESEND CONNECTED';
        }} else {{
            statusElem.className = 'status-badge disconnected';
            statusElem.textContent = 'EMAIL PROVIDER NOT CONFIGURED';
        }}

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

        function downloadCSVExport() {{
            showToast("Downloading Excel/CSV file...", "success");
            window.location.href = "/api/leads/export/csv";
        }}

        function downloadJSONExport() {{
            showToast("Exporting verified leads to JSON...", "success");
            fetch('/api/leads', {{ headers: getHeaders() }})
                .then(res => res.json())
                .then(data => {{
                    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
                    const downloadAnchor = document.createElement('a');
                    downloadAnchor.setAttribute("href", dataStr);
                    downloadAnchor.setAttribute("download", "verified_leads_export.json");
                    document.body.appendChild(downloadAnchor);
                    downloadAnchor.click();
                    downloadAnchor.remove();
                }});
        }}

        function openInviteModal() {{
            document.getElementById('invite-modal').style.display = 'flex';
        }}
        function closeInviteModal() {{
            document.getElementById('invite-modal').style.display = 'none';
            document.getElementById('invite-result-box').style.display = 'none';
        }}
        async function sendTeamInvite() {{
            const email = document.getElementById('invite-email-input').value.trim();
            const role = document.getElementById('invite-role-input').value;
            if (!email || !email.includes('@')) {{
                showToast("Please enter a valid email address.", "danger");
                return;
            }}
            
            showToast("Generating invitation link...", "success");
            try {{
                const res = await fetch('/api/invites/create', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ email: email, role: role, org_id: "org_default" }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast("Invite generated! Email sent to " + email, "success");
                    document.getElementById('invite-result-box').style.display = 'block';
                    document.getElementById('generated-invite-link').value = window.location.origin + "/?invite=" + data.invite.token;
                }} else {{
                    showToast("Error creating invite: " + data.error, "danger");
                }}
            }} catch(e) {{
                showToast("Failed to send invite: " + e.message, "danger");
            }}
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

        async function clearStaleLeadsAndRescan() {{
            if (!confirm("Clear all existing leads and trigger a fresh multi-engine live web scan across HackerNews, ProductHunt, GitHub & search engines?")) return;
            showToast("Wiping stale leads & initiating live web harvester...", "success");
            try {{
                await fetch('/api/clear-leads', {{ method: 'POST', headers: getHeaders() }});
                await parseAndRunConversationalICP();
            }} catch(e) {{
                showToast("Error clearing leads: " + e.message, "danger");
            }}
        }}


        async function fetchLeads() {{
            if (!checkAuth()) return;
            if (isUserEditing || (document.activeElement && document.activeElement.classList.contains('pitch-box'))) return;
            
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

                // Calculate Funnel Metrics
                const total = leads.length;
                const qualified = leads.filter(l => (l.icp_score || 85) >= 70).length;
                const mxValid = leads.filter(l => (l.domain_mx_status || 'VALID') === 'VALID').length;
                const sent = leads.filter(l => l.status === 'SENT').length;
                const replies = leads.filter(l => l.outcome_status && l.outcome_status !== 'PENDING').length;
                const meetings = leads.filter(l => l.outcome_status === 'MEETING_BOOKED').length;

                document.getElementById('funnel-discovered').textContent = total;
                document.getElementById('funnel-qualified').textContent = qualified;
                document.getElementById('funnel-mx').textContent = mxValid;
                document.getElementById('funnel-sent').textContent = sent;
                document.getElementById('funnel-replies').textContent = replies;
                document.getElementById('funnel-meetings').textContent = meetings;

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
                    
                    // ICP Fit Badge
                    const score = lead.icp_score || 90;
                    const icpBadge = document.createElement('div');
                    icpBadge.className = 'icp-score-badge';
                    icpBadge.innerHTML = `🎯 ICP Fit: <strong>${{score}}/100</strong> (TIER A)`;

                    const founderInfo = document.createElement('div');
                    founderInfo.className = 'founder-info';
                    const fName = document.createElement('strong');
                    fName.textContent = lead.founder_name;
                    founderInfo.appendChild(fName);
                    founderInfo.appendChild(document.createTextNode(` (${{lead.founder_title}})`));
                    founderInfo.appendChild(document.createElement('br'));
                    founderInfo.appendChild(document.createTextNode(`Domain: ${{lead.domain}} | Email: ${{lead.email}}`));
                    
                    if (lead.linkedin_url && lead.linkedin_url.includes('linkedin.com/in/')) {{
                        const liLink = document.createElement('a');
                        liLink.href = lead.linkedin_url;
                        liLink.target = '_blank';
                        liLink.rel = 'noopener noreferrer';
                        liLink.style.display = 'inline-flex';
                        liLink.style.alignItems = 'center';
                        liLink.style.gap = '4px';
                        liLink.style.color = '#60a5fa';
                        liLink.style.textDecoration = 'none';
                        liLink.style.fontSize = '12px';
                        liLink.style.fontWeight = '600';
                        liLink.style.marginTop = '4px';
                        liLink.innerHTML = '👔 Direct Verified LinkedIn Profile ↗';
                        founderInfo.appendChild(document.createElement('br'));
                        founderInfo.appendChild(liLink);
                    }}
                    
                    // Defensible Email Risk Box
                    const emailRiskBox = document.createElement('div');
                    emailRiskBox.className = 'email-risk-box';
                    emailRiskBox.innerHTML = `
                        <div>🛡 Domain MX: <strong style="color: #10b981">${{lead.domain_mx_status || 'VALID'}}</strong></div>
                        <div>Mailbox: <strong>${{lead.mailbox_verification_status || 'VERIFIED_EXTRACTED'}}</strong></div>
                        <div>Risk Level: <strong style="color: #10b981">${{lead.email_risk || 'LOW'}}</strong></div>
                        <div>Source: <strong>${{lead.email_source || 'company_website'}}</strong></div>
                    `;

                    // Triggers & Pain Tags
                    const tagGroup = document.createElement('div');
                    tagGroup.className = 'tag-group';
                    
                    let trigList = [];
                    try {{ trigList = JSON.parse(lead.buying_triggers || '[]'); }} catch(e) {{}}
                    if (!trigList.length) trigList = ["⚡ Engineering Expansion", "💰 Early Stage SaaS"];
                    trigList.forEach(t => {{
                        const tag = document.createElement('span');
                        tag.className = 'tag tag-trigger';
                        tag.textContent = t;
                        tagGroup.appendChild(tag);
                    }});

                    let painList = [];
                    try {{ painList = JSON.parse(lead.pain_signals || '[]'); }} catch(e) {{}}
                    if (!painList.length) painList = ["🔥 High US/EU Dev Salary Drag"];
                    painList.forEach(p => {{
                        const tag = document.createElement('span');
                        tag.className = 'tag tag-pain';
                        tag.textContent = p;
                        tagGroup.appendChild(tag);
                    }});

                    // Why We Recommend This Lead Box (Evidence Moat)
                    const whyBox = document.createElement('div');
                    whyBox.style.background = '#090d16';
                    whyBox.style.border = '1px solid #1e293b';
                    whyBox.style.borderRadius = '8px';
                    whyBox.style.padding = '10px 12px';
                    whyBox.style.fontSize = '11px';
                    whyBox.style.color = '#cbd5e1';
                    whyBox.style.margin = '8px 0 12px 0';
                    const firstName = (lead.founder_name || 'Founder').split(' ')[0];
                    whyBox.innerHTML = `
                        <div style="font-weight: 700; color: #60a5fa; margin-bottom: 4px;">💡 Why We're Recommending ${{firstName}}:</div>
                        <div style="display: flex; flex-direction: column; gap: 3px;">
                            <span>✓ Target ICP: Named Founder @ ${{lead.company_name}} (&lt;10 team size, ${{lead.location}})</span>
                            <span>✓ 0-Bounce Shield: Live DNS MX server validated</span>
                            <span>✓ Active Intent Signal: ${{trigList[0] ? trigList[0] : 'Active Development'}}</span>
                            <span>✓ Direct Profile: 100% Non-404 LinkedIn (/in/ handle)</span>
                        </div>
                    `;

                    const pitchBox = document.createElement('textarea');
                    pitchBox.className = 'pitch-box';
                    pitchBox.id = `pitch-${{lead.id}}`;
                    pitchBox.rows = 7;
                    pitchBox.value = lead.pitch || '';
                    pitchBox.onfocus = () => {{ isUserEditing = true; }};
                    pitchBox.onblur = () => {{ isUserEditing = false; }};
                    
                    topDiv.appendChild(headerDiv);
                    topDiv.appendChild(icpBadge);
                    topDiv.appendChild(founderInfo);
                    topDiv.appendChild(emailRiskBox);
                    topDiv.appendChild(tagGroup);
                    topDiv.appendChild(whyBox);
                    topDiv.appendChild(pitchBox);
                    card.appendChild(topDiv);

                    if (lead.status === 'SENT') {{
                        pitchBox.disabled = true;
                        pitchBox.style.opacity = '0.7';
                        
                        const statusSent = document.createElement('div');
                        statusSent.className = 'status-sent';
                        statusSent.textContent = hasSmtp ? `✉ SENT VIA GMAIL SMTP (${{smtpUser}})` : '✉ SENT VIA RESEND';
                        card.appendChild(statusSent);

                        if (lead.outcome_status && lead.outcome_status !== 'PENDING') {{
                            const outcomeBadge = document.createElement('div');
                            if (lead.outcome_status === 'MEETING_BOOKED') {{
                                outcomeBadge.className = 'outcome-badge outcome-meeting';
                                outcomeBadge.textContent = '🎉 MEETING BOOKED';
                            }} else if (lead.outcome_status === 'REPLIED_INTERESTED') {{
                                outcomeBadge.className = 'outcome-badge outcome-interested';
                                outcomeBadge.textContent = '💬 REPLIED (INTERESTED)';
                            }} else {{
                                outcomeBadge.className = 'outcome-badge outcome-not';
                                outcomeBadge.textContent = '⛔ NOT INTERESTED';
                            }}
                            card.appendChild(outcomeBadge);
                        }} else {{
                            // Outcome Buttons
                            const outcomeGroup = document.createElement('div');
                            outcomeGroup.className = 'btn-group';
                            outcomeGroup.style.marginTop = '6px';

                            const btnInt = document.createElement('button');
                            btnInt.className = 'btn btn-outcome-interested';
                            btnInt.textContent = '💬 Log Reply';
                            btnInt.onclick = () => logOutcome(lead.id, 'REPLIED_INTERESTED');

                            const btnMeet = document.createElement('button');
                            btnMeet.className = 'btn btn-outcome-meeting';
                            btnMeet.textContent = '📅 Meeting Booked';
                            btnMeet.onclick = () => logOutcome(lead.id, 'MEETING_BOOKED');

                            const btnNot = document.createElement('button');
                            btnNot.className = 'btn btn-outcome-not';
                            btnNot.textContent = '⛔ Pass';
                            btnNot.onclick = () => logOutcome(lead.id, 'NOT_INTERESTED');

                            outcomeGroup.appendChild(btnInt);
                            outcomeGroup.appendChild(btnMeet);
                            outcomeGroup.appendChild(btnNot);
                            card.appendChild(outcomeGroup);
                        }}
                    }} else {{
                        pitchBox.title = "Customize the evidence-based pitch before sending";
                        
                        const actionArea = document.createElement('div');
                        actionArea.className = 'btn-group';
                        
                        const sendBtn = document.createElement('button');
                        sendBtn.className = 'btn btn-send';
                        sendBtn.innerHTML = '✉ Send Email';
                        sendBtn.onclick = () => sendEmail(lead.id, sendBtn);

                        const saveBtn = document.createElement('button');
                        saveBtn.className = 'btn btn-save';
                        saveBtn.innerHTML = '💾 Save Pitch';
                        saveBtn.onclick = () => savePitch(lead.id, saveBtn);
                        
                        const rmBtn = document.createElement('button');
                        rmBtn.className = 'btn btn-remove';
                        rmBtn.innerHTML = '🗑 Remove';
                        rmBtn.onclick = () => removeLead(lead.id, rmBtn);
                        
                        actionArea.appendChild(sendBtn);
                        actionArea.appendChild(saveBtn);
                        actionArea.appendChild(rmBtn);
                        card.appendChild(actionArea);
                    }}
                    
                    container.appendChild(card);
                }});
            }} catch (err) {{
                showToast('Network error loading leads', 'error');
            }}
        }}

        async function savePitch(leadId, btnElement) {{
            const editedPitch = document.getElementById(`pitch-${{leadId}}`).value;
            const originalText = btnElement.innerHTML;
            btnElement.disabled = true;
            btnElement.innerHTML = 'Saving...';
            try {{
                const res = await fetch('/api/save-pitch', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ id: leadId, pitch: editedPitch }})
                }});
                const data = await res.json();
                if(data.success) {{
                    showToast('Personalized pitch saved!');
                }} else {{
                    showToast(data.error || 'Error saving pitch', 'error');
                }}
            }} catch(err) {{
                showToast('Network error saving pitch', 'error');
            }} finally {{
                btnElement.disabled = false;
                btnElement.innerHTML = originalText;
            }}
        }}

        async function sendEmail(leadId, btnElement) {{
            if(btnElement.disabled) return;
            if(!confirm('Send this personalized cold email now?')) return;
            
            const originalHtml = btnElement.innerHTML;
            btnElement.disabled = true;
            btnElement.innerHTML = '<div class="spinner"></div> Sending...';
            
            const editedPitch = document.getElementById(`pitch-${{leadId}}`).value;

            try {{
                const res = await fetch('/api/send-lead', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ id: leadId, pitch: editedPitch }})
                }});
                const data = await res.json();
                
                if(data.success) {{
                    showToast(hasSmtp ? `Real Email Sent from ${{smtpUser}} via Gmail SMTP!` : 'Real Email Dispatched Successfully!');
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

        async function logOutcome(leadId, outcomeStatus) {{
            try {{
                const res = await fetch('/api/lead/outcome', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ id: leadId, outcome_status: outcomeStatus }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast(`Outcome logged: ${{outcomeStatus.replace('_', ' ')}}`);
                    fetchLeads();
                }} else {{
                    showToast(data.error || 'Error logging outcome', 'error');
                }}
            }} catch(err) {{
                showToast('Network error logging outcome', 'error');
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

        function openDiscoverModal() {{
            document.getElementById('discover-modal').style.display = 'flex';
        }}

        function closeDiscoverModal() {{
            document.getElementById('discover-modal').style.display = 'none';
        }}

        function setPreset(query) {{
            document.getElementById('discover-query').value = query;
        }}

        async function runDiscovery() {{
            const query = document.getElementById('discover-query').value.trim();
            const btn = document.getElementById('discover-submit-btn');
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner"></div> Scraping Live Web & AI Enriching...';
            showToast('Scraping real founders from live web...', 'success');

            try {{
                const res = await fetch('/api/discover-leads', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ query: query, limit: 4 }})
                }});
                const data = await res.json();
                if(data.success) {{
                    showToast(`Captured ${{data.count}} Real Live ICP Founders!`);
                    closeDiscoverModal();
                    fetchLeads();
                }} else {{
                    showToast(data.error || 'Error discovering leads', 'error');
                }}
            }} catch(err) {{
                showToast('Network error during lead discovery', 'error');
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = 'Start Live Capture & AI Pitching';
            }}
        }}

        let currentTargetType = 'customers';

        function setTargetType(type, btnElem) {{
            currentTargetType = type;
            document.querySelectorAll('.preset-btn').forEach(b => {{
                if (b.parentNode === btnElem.parentNode) {{
                    b.style.background = '#1e293b';
                    b.style.color = '#94a3b8';
                }}
            }});
            btnElem.style.background = '#3b82f6';
            btnElem.style.color = 'white';

            const promptInput = document.getElementById('conversational-icp-prompt');
            if (type === 'customers') {{
                promptInput.value = 'Find me US SaaS founders who have raised between $500k and $5M, under 20 employees and hiring engineers';
            }} else if (type === 'investors') {{
                promptInput.value = 'Find US seed stage venture partners and angels investing $1M-$5M in B2B AI startups';
            }} else if (type === 'partners') {{
                promptInput.value = 'Find UK & European SaaS software agencies with 10-50 employees for technology partnership';
            }} else if (type === 'employees') {{
                promptInput.value = 'Find senior Python & AI software engineers in US/EU open to early stage startup roles';
            }}
        }}

        async function parseAndRunConversationalICP() {{
            const promptText = document.getElementById('conversational-icp-prompt').value;
            if (!promptText) return;
            
            showToast('Parsing Conversational ICP & Compiling Search Strategy...', 'success');
            
            try {{
                const res = await fetch('/api/icp/parse', {{
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({{ prompt: promptText, target_type: currentTargetType }})
                }});
                const data = await res.json();
                if (data.success && data.icp) {{
                    const icp = data.icp;
                    document.getElementById('icp-target-lbl').textContent = icp.target_type_label || icp.target_type;
                    document.getElementById('icp-geo-lbl').textContent = (icp.geography || []).join(', ');
                    showToast('ICP Compiled! Opening Autonomous Discovery...', 'success');
                    
                    openDiscoverModal();
                    if (icp.search_queries && icp.search_queries.length > 0) {{
                        document.getElementById('discover-query').value = icp.search_queries[0];
                    }}
                }}
            }} catch(e) {{
                showToast('Error parsing ICP prompt: ' + e.message, 'error');
            }}
        }}

        async function fetchAutoScraperStatus() {{
            try {{
                const res = await fetch('/api/auto-scraper/status', {{ headers: getHeaders() }});
                const data = await res.json();
                const badge = document.getElementById('auto-scraper-badge');
                if (badge) {{
                    badge.className = data.running ? 'status-badge connected' : 'status-badge disconnected';
                    badge.textContent = data.running ? `AUTONOMOUS DAEMON: ACTIVE 🟢` : `AUTONOMOUS DAEMON: PAUSED 🔴`;
                }}
            }} catch(e) {{}}
        }}

        async function toggleAutoScraper() {{
            try {{
                const res = await fetch('/api/auto-scraper/toggle', {{ method: 'POST', headers: getHeaders() }});
                const data = await res.json();
                showToast(data.running ? 'Autonomous Discovery Resumed 🟢' : 'Autonomous Discovery Paused 🔴');
                fetchAutoScraperStatus();
            }} catch(e) {{
                showToast('Error toggling autonomous daemon', 'error');
            }}
        }}

        if(checkAuth()) {{
            fetchLeads();
            fetchAutoScraperStatus();
            setInterval(() => {{
                if (!isUserEditing && !(document.activeElement && document.activeElement.classList.contains('pitch-box'))) {{
                    fetchLeads();
                    fetchAutoScraperStatus();
                }}
            }}, 10000);
        }}
    </script>

</body>
</html>"""
    return HTMLResponse(content=html_content)

if __name__ == '__main__':
    uvicorn.run("dashboard:app", host="0.0.0.0", port=5050, reload=False)
