import time
import uuid
import logging
import threading
from typing import Dict, Any

from scraper import StartupLeadScraper
from enricher import AIProspectEnricher
from crm_client import CompAICRMClient
from database import add_lead, get_all_leads

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ICPBackgroundWorker")


class ICPBackgroundWorker:
    """
    Autonomous background worker for Pre-Seed / Seed SaaS founders (<10 team).
    Continuously searches target locations (US, AUS, EU, Dubai), enriches pitches,
    logs to Comp AI CRM, and populates SQLite database for human approval.
    """

    def __init__(self, interval_seconds: int = 300):
        self.interval_seconds = interval_seconds
        self.scraper = StartupLeadScraper()
        self.enricher = AIProspectEnricher()
        self.crm = CompAICRMClient()
        
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
            "Y Combinator B2B SaaS founder US AUS EU Dubai",
            "Pre-seed SaaS startup founder San Francisco Sydney Dubai",
            "Early stage SaaS founder CEO team under 10",
            "Angel invested SaaS startup CEO Sydney Dubai San Francisco"
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

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "running": self.is_running(),
            "status": "ACTIVE 🟢" if self.is_running() else "STOPPED 🔴",
            "total_discovered": self.stats["total_discovered"],
            "last_run": self.stats["last_run"],
            "current_query": self.stats["current_query"]
        }

    def _run_loop(self):
        """Main execution loop."""
        # Initial wait of 5 seconds on startup
        time.sleep(5)

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

                new_count = 0
                for lead in raw_leads:
                    domain = lead.get("domain", "").lower()
                    if not domain or domain in existing_domains:
                        continue

                    # 1. AI Pitch Personalization First
                    if not lead.get("pitch"):
                        pitch = self.enricher.generate_pitch(
                            founder_name=lead["founder_name"],
                            company_name=lead["company_name"],
                            location=lead["location"],
                            summary=lead["tech_summary"]
                        )
                        lead["pitch"] = pitch

                    # 2. Strict Email Deliverability Verification
                    from scraper import verify_strict_email_deliverability
                    deliv_check = verify_strict_email_deliverability(
                        email=lead["email"],
                        domain=lead["domain"],
                        founder_name=lead["founder_name"]
                    )
                    
                    lead["deliverability_score"] = deliv_check["score"]
                    lead["deliverability_status"] = deliv_check["status"]

                    if not deliv_check["valid"]:
                        logger.info(f"[ICP Worker Daemon] Skipped {domain}: Low deliverability ({deliv_check['score']}%) - {deliv_check['reasons']}")
                        lead["status"] = "LOW_DELIVERABILITY_FLAGGED"
                        add_lead(lead)
                        continue

                    # 3. Log to Comp AI CRM
                    try:
                        comp_rec = self.crm.create_or_update_company(
                            name=lead["company_name"],
                            domain=lead["domain"],
                            location=lead["location"],
                            summary=lead["tech_summary"]
                        )
                        self.crm.create_or_update_contact(
                            company_id=comp_rec.get("id", "comp_temp"),
                            name=lead["founder_name"],
                            email=lead["email"],
                            title=lead["founder_title"],
                            pitch_draft=lead["pitch"]
                        )
                    except Exception as crm_err:
                        logger.warning(f"[ICP Worker Daemon] CRM log warning: {crm_err}")

                    # 4. Promote to Human-in-the-Loop Dashboard for Final Email Review
                    lead["status"] = "DRAFT_REVIEW"

                    # 5. Save to Database for Dashboard Display
                    add_lead(lead)
                    existing_domains.add(domain)
                    new_count += 1
                    self.stats["total_discovered"] += 1

                logger.info(f"[ICP Worker Daemon] Batch finished. Added {new_count} new real ICP leads.")

            except Exception as e:
                logger.error(f"[ICP Worker Daemon] Error during discovery cycle: {e}")

            self._query_index += 1

            # Wait for next interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                break


# Global singleton instance
worker_instance = ICPBackgroundWorker(interval_seconds=300)
