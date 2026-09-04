import requests
import logging
from typing import Dict, Any, Optional
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CompAICRM")

class CompAICRMClient:
    """
    Integration Client for trycompai/crm (Comp AI Agentic CRM).
    Allows autonomous agents to log companies, contacts, research evidence, and lead stages.
    """
    def __init__(self, api_url: str = settings.CRM_API_URL, api_key: str = settings.CRM_API_KEY):
        self.api_url = api_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def create_or_update_company(self, name: str, domain: str, location: str, summary: str) -> Optional[Dict[str, Any]]:
        """Creates or updates a target startup company in Comp AI CRM."""
        endpoint = f"{self.api_url}/companies"
        payload = {
            "name": name,
            "domain": domain,
            "location": location,
            "metadata": {
                "summary": summary,
                "source": "AI_Lead_Agent"
            }
        }
        try:
            logger.info(f"[CompAI CRM] Logging company record for {name} ({domain})...")
            # Fallback mock for local testing if CRM server isn't live yet
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=5)
            if response.status_code in [200, 201]:
                return response.json()
        except Exception as e:
            logger.warning(f"[CompAI CRM] Local CRM server offline ({e}). Operating in standalone/log mode.")
        
        return {"id": f"comp_{domain}", "name": name, "domain": domain, "status": "LOGGED_LOCAL"}

    def create_or_update_contact(self, company_id: str, name: str, email: str, title: str, pitch_draft: str) -> Optional[Dict[str, Any]]:
        """Logs a lead contact (Founder/CTO) in Comp AI CRM with evidence and personalized pitch."""
        endpoint = f"{self.api_url}/contacts"
        payload = {
            "companyId": company_id,
            "name": name,
            "email": email,
            "title": title,
            "status": "NEW_LEAD",
            "notes": f"AI Personalized Pitch:\n{pitch_draft}"
        }
        try:
            logger.info(f"[CompAI CRM] Logging contact {name} <{email}>...")
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=5)
            if response.status_code in [200, 201]:
                return response.json()
        except Exception as e:
            logger.warning(f"[CompAI CRM] Local CRM server offline ({e}).")

        return {"id": f"contact_{email}", "name": name, "email": email, "status": "NEW_LEAD"}

    def log_interaction(self, contact_id: str, action_type: str, content: str):
        """Logs email outreach, responses, or follow-ups in Comp AI CRM's durable memory."""
        logger.info(f"[CompAI CRM] Logging interaction '{action_type}' for contact {contact_id}.")
        endpoint = f"{self.api_url}/interactions"
        payload = {
            "contactId": contact_id,
            "type": action_type, # e.g. 'EMAIL_SENT', 'REPLY_RECEIVED'
            "content": content
        }
        try:
            requests.post(endpoint, json=payload, headers=self.headers, timeout=5)
        except Exception:
            pass
