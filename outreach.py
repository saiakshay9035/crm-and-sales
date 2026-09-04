import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings
from mcp_outreach import ComposioMCPOutreachManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EmailOutreach")

class EmailOutreachManager:
    """
    Handles automated email dispatch via Composio MCP / SMTP.
    Includes dry-run protection mode for testing without sending real emails accidentally.
    """
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.composio_mcp = ComposioMCPOutreachManager(api_key=settings.COMPOSIO_API_KEY)

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

        # Live dispatch via Composio MCP Gateway
        try:
            logger.info(f"[Email Engine (LIVE VIA COMPOSIO)] Sending email to {to_email} via Composio Gmail...")
            success = self.composio_mcp.send_email_via_composio(
                recipient=to_email,
                subject=subject,
                body=body
            )
            if success:
                logger.info(f"[Email Engine] Live email successfully dispatched to {to_email}!")
                return True
        except Exception as e:
            logger.error(f"[Email Engine] Composio dispatch error: {e}. Attempting fallback SMTP.")
            
        # Fallback SMTP dispatch if configured
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
