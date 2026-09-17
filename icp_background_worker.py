import logging
import threading
import time
from typing import Any, List

from database import add_lead, get_all_leads
from enricher import AIProspectEnricher
from scraper import StartupLeadScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ICPBackgroundWorker")


class ICPBackgroundWorker:
    """
    Universal autonomous background worker for lead discovery.
    Continuously searches for prospects matching user-defined ICP criteria,
    enriches with AI pitches, and populates SQLite database for human approval.
    """

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self.scraper = StartupLeadScraper()
        self.enricher = AIProspectEnricher()
        
        self._thread = None
        self._stop_event = threading.Event()
        self._is_active = False
        
        self.stats = {
            "total_discovered": 0,
            "last_run": None,
            "status": "STOPPED",
            "current_query": ""
        }

        self.queries = [
            "B2B startup founder CEO contact email",
            "small business owner managing director contact",
            "tech company founder CEO US Europe email",
            "SaaS startup co-founder CTO contact",
            "startup founder CEO Sydney Dubai London email",
            "growing company CEO founder contact email",
            "venture backed startup founder contact"
        ]
        self._query_index = 0

    def start(self):
        """Starts the background worker thread."""
        if self._is_active and self._thread and self._thread.is_alive():
            logger.info("[ICP Worker] Worker is already running.")
            return

        self._stop_event.clear()
        self._is_active = True
        self.stats["status"] = "RUNNING"
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"[ICP Worker] Started background discovery daemon (Interval: {self.interval_seconds}s).")

    def stop(self):
        """Stops the background worker thread."""
        self._is_active = False
        self._stop_event.set()
        self.stats["status"] = "STOPPED"
        logger.info("[ICP Worker] Stopping background discovery daemon...")

    def is_running(self) -> bool:
        return self._is_active and self._thread is not None and self._thread.is_alive()

    def get_status_dict(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "status": "ACTIVE 🟢" if self.is_running() else "STOPPED 🔴",
            "total_discovered": self.stats["total_discovered"],
            "last_run": self.stats["last_run"],
            "current_query": self.stats["current_query"]
        }

    def set_queries(self, queries: List[str]):
        """Dynamically updates background search queries based on active ICP prompt."""
        if queries:
            self.queries = queries
            self._query_index = 0
            logger.info(f"[ICP Worker] Dynamically updated search queries ({len(queries)} queries active): {queries[:2]}...")

    def send_lead_alert_email(self, lead: dict):
        """Sends instant real-time email notification when a new ICP lead is verified."""
        try:
            from email_service import EmailService
            from config import settings
            target_email = getattr(settings, 'SMTP_USER', '')
            if not target_email or "@" not in target_email or "domain.com" in target_email:
                return
            
            email_svc = EmailService()
            subject = f"⚡ New ICP Lead Verified: {lead.get('founder_name')} @ {lead.get('company_name')}"
            html_body = f"""
            <div style="font-family: system-ui, sans-serif; background: #0b1120; color: #f3f4f6; padding: 24px; border-radius: 12px;">
                <h2 style="color: #38bdf8; margin-top: 0;">⚡ New Verified ICP Lead Discovered!</h2>
                <div style="background: #1e293b; padding: 16px; border-radius: 8px; border: 1px solid #334155;">
                    <h3 style="margin: 0 0 8px 0; color: #f8fafc;">{lead.get('founder_name')} ({lead.get('founder_title', 'Founder & CEO')})</h3>
                    <p style="margin: 4px 0; color: #94a3b8;"><strong>Company:</strong> {lead.get('company_name')} ({lead.get('domain')})</p>
                    <p style="margin: 4px 0; color: #94a3b8;"><strong>Email:</strong> <span style="color: #34d399;">{lead.get('email')}</span> (Verified MX & Deliverable)</p>
                    <p style="margin: 4px 0; color: #94a3b8;"><strong>LinkedIn:</strong> <a href="{lead.get('linkedin_url')}" style="color: #60a5fa;">{lead.get('linkedin_url')}</a></p>
                    <p style="margin: 4px 0; color: #94a3b8;"><strong>Location:</strong> {lead.get('location')}</p>
                    <p style="margin: 12px 0 4px 0; color: #cbd5e1; font-style: italic;">"{lead.get('tech_summary')}"</p>
                </div>
                <div style="margin-top: 16px;">
                    <a href="http://localhost:5050" style="background: #3b82f6; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Open Dashboard & Approve Outreach →</a>
                </div>
            </div>
            """
            email_svc.send(target_email, subject, html_body, f"New ICP Lead: {lead.get('founder_name')} @ {lead.get('company_name')} ({lead.get('email')})")
            logger.info(f"[ICP Worker Daemon] Sent real-time lead alert email to {target_email} for {lead.get('founder_name')} @ {lead.get('company_name')}")
        except Exception as e:
            logger.warning(f"[ICP Worker Daemon] Failed to send real-time lead alert email: {e}")

    def _run_loop(self):
        """Main execution loop."""
        time.sleep(2)

        while not self._stop_event.is_set():
            query = self.queries[self._query_index % len(self.queries)]
            self.stats["current_query"] = query
            self.stats["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")

            logger.info(f"[ICP Worker Daemon] Running automated discovery for: '{query}'...")

            try:
                # 1. Scrape real ICP leads
                raw_leads = self.scraper.search_real_leads(query=query, limit=3)

                # Get existing domains to prevent duplicates
                existing_leads = get_all_leads()
                existing_domains = {l.get("domain", "").lower() for l in existing_leads if l.get("domain")}

                unseen_raw = [l for l in raw_leads if l.get("domain", "").lower() not in existing_domains]
                if not unseen_raw:
                    logger.info(f"[ICP Worker Daemon] Live discovery yielded 0 new unseen domains for query '{query}'. Sleeping until next cycle...")
                    self._query_index += 1
                    time.sleep(self.interval_seconds)
                    continue

                raw_leads = unseen_raw

                new_count = 0
                for lead in raw_leads:
                    domain = lead.get("domain", "").lower()
                    if not domain or domain in existing_domains:
                        continue

                    # 2. AI Pitch Personalization First
                    if not lead.get("pitch"):
                        pitch = self.enricher.generate_pitch(
                            founder_name=lead["founder_name"],
                            company_name=lead["company_name"],
                            location=lead["location"],
                            summary=lead["tech_summary"]
                        )
                        lead["pitch"] = pitch

                    # 3. Strict Email Deliverability Verification
                    from scraper import verify_strict_email_deliverability
                    deliv_check = verify_strict_email_deliverability(
                        email=lead["email"],
                        domain=lead["domain"],
                        founder_name=lead["founder_name"],
                        linkedin_url=lead.get("linkedin_url", ""),
                        company_name=lead.get("company_name", ""),
                        founder_title=lead.get("founder_title", ""),
                        tech_summary=lead.get("tech_summary", "")
                    )
                    
                    lead["deliverability_score"] = deliv_check["score"]
                    lead["deliverability_status"] = deliv_check["status"]

                    if not deliv_check["valid"]:
                        logger.info(f"[ICP Worker Daemon] Skipped {domain}: Low deliverability ({deliv_check['score']}%) - {deliv_check['reasons']}")
                        lead["status"] = "LOW_DELIVERABILITY_FLAGGED"
                        add_lead(lead)
                        continue

                    # 4. Promote to Human-in-the-Loop Dashboard for Final Email Review
                    lead["status"] = "DRAFT_REVIEW"

                    # 5. Save to Database for Dashboard Display
                    add_lead(lead)
                    existing_domains.add(domain)
                    new_count += 1
                    self.stats["total_discovered"] += 1

                    # 6. Send instant real-time lead alert email notification
                    self.send_lead_alert_email(lead)

                logger.info(f"[ICP Worker Daemon] Batch finished. Added {new_count} new real ICP leads.")

            except Exception as e:
                logger.error(f"[ICP Worker Daemon] Error during discovery cycle: {e}")

            self._query_index += 1

            # Wait for next interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                break


# Global singleton instance
worker_instance = ICPBackgroundWorker(interval_seconds=60)
