import logging
from config import settings
from email_service import EmailService, EmailServiceError as EmailError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EmailOutreach")

class EmailOutreachManager:
    """
    Handles automated live email dispatch via EmailService.
    Includes dry-run protection mode for testing.
    """
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.email_service = EmailService()

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

        html_body = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            {body.replace(chr(10), '<br>')}
        </div>
        """

        try:
            logger.info(f"[Email Engine (LIVE)] Dispatching email to {to_email}...")
            return self.email_service.send(to_email, subject, html_body, body)
        except EmailError as e:
            logger.error(f"[Email Engine] Failed to send email to {to_email}: {e}")
            return False
