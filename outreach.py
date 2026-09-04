import requests
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EmailOutreach")

class EmailOutreachManager:
    """
    Handles automated live email dispatch via Resend API, Composio, or SMTP.
    Includes dry-run protection mode for testing.
    """
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.resend_api_key = settings.RESEND_API_KEY
        self.resend_from = settings.RESEND_FROM_EMAIL

    def send_email(self, to_email: str, pitch_content: str) -> bool:
        lines = pitch_content.strip().split("\n")
        subject = "Quick question regarding tech delivery"
        body = pitch_content

        if lines[0].startswith("Subject:"):
            subject = lines[0].replace("Subject:", "").strip()
            body = "\n".join(lines[1:]).strip()

        logger.info(f"[Email Engine] Target: {to_email} | Subject: '{subject}'")

        if self.dry_run:
            logger.info(f"[Email Engine (DRY RUN)] Email queued & logged successfully for {to_email}.")
            return True

        # 1. Primary Live Dispatch via Resend API
        if self.resend_api_key:
            try:
                logger.info(f"[Email Engine (RESEND LIVE)] Dispatching email to {to_email}...")
                url = "https://api.resend.com/emails"
                headers = {
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                }
                
                # HTML formatted body
                html_body = f"""
                <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    {body.replace(chr(10), '<br>')}
                </div>
                """
                
                payload = {
                    "from": self.resend_from,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body
                }
                
                res = requests.post(url, headers=headers, json=payload, timeout=10)
                if res.status_code in [200, 201]:
                    logger.info(f"[Email Engine] Live email successfully delivered to {to_email}! Resend ID: {res.json().get('id')}")
                    return True
                else:
                    logger.warning(f"[Email Engine] Resend API Warning ({res.status_code}): {res.text}")
            except Exception as e:
                logger.error(f"[Email Engine] Resend exception ({e}). Falling back to SMTP.")

        # 2. Fallback SMTP dispatch
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_USER
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.send_message(msg)

            logger.info(f"[Email Engine] Email successfully sent to {to_email} via SMTP!")
            return True
        except Exception as e:
            logger.error(f"[Email Engine] Failed to send email to {to_email}: {e}")
            return False
