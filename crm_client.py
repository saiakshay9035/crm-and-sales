import logging
import os
import uuid
from typing import Any

import psycopg2

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CompAICRM")

class CRMError(Exception):
    """Custom exception for CRM-related errors."""

class CompAICRMClient:
    """
    Direct Neon PostgreSQL Integration Client for Comp AI CRM.
    Captures companies, contacts, pitches, and outreach activities directly into Neon DB.
    """
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or getattr(settings, "NEON_DSN", "") or os.environ.get("NEON_DSN", "")


    def _get_connection(self):
        return psycopg2.connect(self.dsn)

    def _get_default_author_id(self, cur) -> str:
        try:
            cur.execute('SELECT id FROM "user" LIMIT 1;')
            row = cur.fetchone()
            if row:
                return row[0]
        except Exception:
            pass
        return "seed-ada-okafor"

    def create_or_update_company(self, name: str, domain: str, location: str, summary: str) -> dict[str, Any]:
        """
        Creates or updates a target startup company directly in Neon PostgreSQL.
        """
        logger.info(f"[CompAI CRM] Logging company record for {name} ({domain}) in Neon DB...")
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    author_id = self._get_default_author_id(cur)
                    
                    if domain:
                        cur.execute('SELECT id, name, domain FROM company WHERE domain = %s AND "archivedAt" IS NULL LIMIT 1;', (domain,))
                        row = cur.fetchone()
                        if row:
                            return {"id": row[0], "name": row[1], "domain": row[2], "status": "EXISTING"}
                    
                    comp_id = f"cl{uuid.uuid4().hex[:20]}"
                    website = f"https://{domain}" if domain else None
                    
                    cur.execute(
                        """
                        INSERT INTO company (id, name, domain, website, city, description, "ownerId", source, "createdAt", "updatedAt")
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'IMPORT', NOW(), NOW())
                        RETURNING id, name, domain;
                        """,
                        (comp_id, name, domain, website, location, summary, author_id)
                    )
                    row = cur.fetchone()
                    conn.commit()
                    logger.info(f"[CompAI CRM] Successfully created company {name} ({comp_id}) in Neon DB.")
                    return {"id": row[0], "name": row[1], "domain": row[2], "status": "CREATED"}
        except Exception as e:
            logger.warning(f"[CompAI CRM] Direct Neon DB log warning for company {name}: {e}.")
            return {"id": f"comp_{domain}", "name": name, "domain": domain, "status": "LOGGED_LOCAL"}

    def create_or_update_contact(self, company_id: str, name: str, email: str, title: str, pitch_draft: str) -> dict[str, Any]:
        """
        Logs a lead contact (Founder/CTO) in Neon DB with AI pitch note.
        """
        logger.info(f"[CompAI CRM] Logging contact {name} <{email}> in Neon DB...")
        parts = (name or "").strip().split(" ")
        first_name = parts[0] or "Founder"
        last_name = " ".join(parts[1:]) if len(parts) > 1 else None

        actual_comp_id = company_id if company_id and not company_id.startswith("comp_") else None

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    author_id = self._get_default_author_id(cur)
                    
                    if email:
                        cur.execute('SELECT id, email FROM contact WHERE email = %s AND "archivedAt" IS NULL LIMIT 1;', (email,))
                        row = cur.fetchone()
                        if row:
                            return {"id": row[0], "email": row[1], "status": "EXISTING"}

                    contact_id = f"cl{uuid.uuid4().hex[:20]}"
                    cur.execute(
                        """
                        INSERT INTO contact (id, "firstName", "lastName", email, title, "companyId", "ownerId", source, "createdAt", "updatedAt")
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'IMPORT', NOW(), NOW())
                        RETURNING id, email;
                        """,
                        (contact_id, first_name, last_name, email, title, actual_comp_id, author_id)
                    )
                    c_row = cur.fetchone()

                    # Add pitch note activity if provided
                    if pitch_draft and c_row:
                        act_id = f"cl{uuid.uuid4().hex[:20]}"
                        cur.execute(
                            """
                            INSERT INTO activity (id, type, body, "contactId", "companyId", "createdById", "createdAt", "updatedAt")
                            VALUES (%s, 'NOTE', %s, %s, %s, %s, NOW(), NOW());
                            """,
                            (act_id, f"AI Personalized Pitch:\n{pitch_draft}", c_row[0], actual_comp_id, author_id)
                        )

                    conn.commit()
                    logger.info(f"[CompAI CRM] Successfully created contact {name} ({contact_id}) in Neon DB.")
                    return {"id": c_row[0], "email": c_row[1], "status": "CREATED"}
        except Exception as e:
            logger.warning(f"[CompAI CRM] Direct Neon DB log warning for contact {name}: {e}.")
            return {"id": f"contact_{email}", "name": name, "email": email, "status": "NEW_LEAD"}

    def log_interaction(self, contact_id: str, action_type: str, content: str) -> None:
        """
        Logs outreach activities in Neon DB.
        """
        logger.info(f"[CompAI CRM] Logging interaction '{action_type}' for contact {contact_id} in Neon DB.")
        try:
            actual_contact_id = contact_id if contact_id and not contact_id.startswith("contact_") else None
            if not actual_contact_id:
                return

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    author_id = self._get_default_author_id(cur)
                    act_id = f"cl{uuid.uuid4().hex[:20]}"
                    cur.execute(
                        """
                        INSERT INTO activity (id, type, body, "contactId", "createdById", "createdAt", "updatedAt")
                        VALUES (%s, 'EMAIL', %s, %s, %s, NOW(), NOW());
                        """,
                        (act_id, f"Outreach Action [{action_type}]:\n{content}", actual_contact_id, author_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.warning(f"[CompAI CRM] Failed to log interaction in Neon DB: {e}.")
