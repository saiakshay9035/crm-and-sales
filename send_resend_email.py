import logging
import os
import sys

from email_service import EmailError, EmailService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResendEmail")

def send_real_email(recipient_email: str):
    logger.info(f"[Resend API] Sending real test email to {recipient_email}...")
    
    email_service = EmailService()
    subject = "🚀 Live Test: Autonomous AI Lead & Outreach Agent"
    html_body = """
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #6366f1;">🚀 Live Test Successful!</h2>
        <p>Hi there,</p>
        <p>This is a <strong>REAL live email</strong> sent from your Autonomous AI Lead Generation & Outreach Agent via Resend API!</p>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <h3>System Status:</h3>
        <ul>
            <li><strong>Resend API</strong>: Connected & Live</li>
            <li><strong>Target ICP</strong>: Founders in US, UAE, Australia, and EU</li>
            <li><strong>Core Offer</strong>: Senior Indian Tech Talent + End-to-End Product & Project Management</li>
            <li><strong>GitHub Repository</strong>: <a href="https://github.com/saiakshay9035/crm-and-sales">saiakshay9035/crm-and-sales</a></li>
            <li><strong>Local CRM Dashboard</strong>: <a href="http://localhost:5000">http://localhost:5000</a></li>
        </ul>
        <p>Your pipeline is fully active and ready to deliver leads and outreach on autopilot!</p>
        <p>Best regards,<br><strong>Autonomous AI Lead Agent</strong></p>
    </div>
    """
    
    try:
        # Use send_via_resend specifically to test Resend API functionality
        result = email_service.send_via_resend(
            to_email=recipient_email,
            subject=subject,
            body_html=html_body,
            body_text="Live Test Successful! System is active."
        )
        if result:
            print("\n=======================================================")
            print(f"🎉 SUCCESS! REAL EMAIL SENT TO {recipient_email}!")
            print(f"Check your Inbox / Spam folder at {recipient_email} right now!")
            print("=======================================================\n")
            return True
        return False
    except EmailError as e:
        logger.error(f"[Resend API] Error sending email: {e}")
        return False
    except Exception as e:
        logger.error(f"[Resend API] Request Exception: {e}")
        return False

if __name__ == "__main__":
    email = None
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        email = os.getenv("TEST_EMAIL")
        
    if not email:
        print("Usage: python send_resend_email.py <recipient_email>")
        print("Or set TEST_EMAIL environment variable.")
        sys.exit(1)
        
    send_real_email(email)
