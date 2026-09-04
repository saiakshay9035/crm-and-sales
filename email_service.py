import logging
import smtplib
from email.message import EmailMessage

import requests

from config import settings

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Custom exception for email sending errors."""


# Alias for backward compatibility
EmailError = EmailServiceError


class EmailService:
    """
    Centralized email dispatch service.
    Supports Resend API (primary) and SMTP (fallback).
    Automatically appends CAN-SPAM compliant footer to all outbound emails.
    """

    def __init__(
        self,
        resend_api_key: str | None = None,
        from_email: str | None = None,
        business_address: str | None = None,
    ):
        self.resend_api_key = resend_api_key if resend_api_key is not None else settings.RESEND_API_KEY
        self.resend_from = from_email if from_email is not None else settings.RESEND_FROM_EMAIL
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_pass = settings.SMTP_PASS
        self.business_address = business_address if business_address is not None else settings.BUSINESS_ADDRESS

    def _append_can_spam_footer(self, body_html: str) -> str:
        """Appends a CAN-SPAM compliant footer to the HTML email body."""
        footer_html = f"""
        <br><br>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 11px; color: #999;">
            You received this email because we thought our services might be relevant to your business.
            <br><a href="#unsubscribe" style="color: #999;">Unsubscribe</a> | {self.business_address}
        </p>
        """
        return body_html + footer_html

    def send_via_resend(self, to_email: str, subject: str, body_html: str) -> dict:
        """Send email via Resend API. Returns the Resend API response dict."""
        if not self.resend_api_key:
            raise EmailServiceError("RESEND_API_KEY is not configured")

        html_with_footer = self._append_can_spam_footer(body_html)

        headers = {
            "Authorization": f"Bearer {self.resend_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "from": self.resend_from,
            "to": [to_email],
            "subject": subject,
            "html": html_with_footer,
        }

        try:
            response = requests.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully sent email to {to_email} via Resend. ID: {result.get('id')}")
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to send email to {to_email} via Resend: {e}")
            raise EmailServiceError(f"Resend API error: {e}")

    def send_via_smtp(self, to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        """Send email via SMTP. Returns True on success."""
        if not self.smtp_user or self.smtp_user == "your_email@domain.com" or not self.smtp_pass:
            raise EmailServiceError("SMTP credentials are not configured")

        footer_text = (
            f"\n\n--\nYou received this because we thought our services "
            f"might be relevant.\nUnsubscribe: #unsubscribe\n{self.business_address}"
        )
        body_with_footer = body_text + footer_text

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = to_email
        msg.set_content(body_with_footer)

        if body_html:
            html_with_footer = self._append_can_spam_footer(body_html)
            msg.add_alternative(html_with_footer, subtype="html")

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            logger.info(f"Successfully sent email to {to_email} via SMTP ({self.smtp_user}).")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email} via SMTP: {e}")
            raise EmailServiceError(f"SMTP error: {e}")

    def send(self, to_email: str, subject: str, body_html: str, body_text: str = "") -> bool:
        """
        Primary dispatch method. Tries SMTP (Gmail) first if configured, falls back to Resend API.
        Returns True on success.
        """
        has_smtp = bool(self.smtp_user and self.smtp_user != "your_email@domain.com" and self.smtp_pass)
        
        # If SMTP (Gmail) is configured, try SMTP first
        if has_smtp:
            try:
                return self.send_via_smtp(to_email, subject, body_text or body_html, body_html)
            except EmailServiceError as e:
                logger.warning(f"SMTP failed ({e}), falling back to Resend API.")

        # Try Resend API as fallback or primary
        if self.resend_api_key:
            try:
                self.send_via_resend(to_email, subject, body_html)
                return True
            except EmailServiceError as e:
                logger.warning(f"Resend failed ({e}).")

        # Final try SMTP if not tried yet
        if not has_smtp:
            try:
                return self.send_via_smtp(to_email, subject, body_text or body_html, body_html)
            except EmailServiceError:
                pass

        raise EmailServiceError(f"All email dispatch methods failed for {to_email}.")
