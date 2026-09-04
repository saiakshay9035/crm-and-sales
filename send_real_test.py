import os
import sys
import logging
from config import settings
from composio import ComposioToolSet, Action, App

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RealEmailTest")

def send_real_test_email(recipient_email: str):
    logger.info(f"[Real Test] Attempting live email dispatch to {recipient_email}...")
    
    composio_toolset = ComposioToolSet(api_key=settings.COMPOSIO_API_KEY)
    
    subject = "🚀 Live Test: Autonomous AI Lead & Outreach Agent"
    body = f"""Hi there,

This is a real live test email sent from your Autonomous AI Lead Generation Agent!

Agent Status:
- Composio API Key: Connected ({settings.COMPOSIO_API_KEY[:8]}...)
- Target Market: US, UAE, Australia, EU Startups
- Core Offer: Senior Indian Developers + End-to-End Product & Project Management
- Local Dashboard: http://localhost:5000
- GitHub Repo: https://github.com/saiakshay9035/crm-and-sales

Your pipeline is fully active and ready to scale outreach!

Best regards,
Autonomous AI Lead Agent
"""

    try:
        # Execute Gmail send mail tool via Composio
        result = composio_toolset.execute_action(
            action=Action.GMAIL_SEND_MAIL,
            params={
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body
            }
        )
        logger.info(f"[Real Test] Result from Composio: {result}")
        print("\n=======================================================")
        print(f"SUCCESS: Test email request dispatched to {recipient_email}!")
        print(f"Check your Inbox / Spam folder at {recipient_email}")
        print("=======================================================\n")
        return result
    except Exception as e:
        logger.error(f"[Real Test] Composio Execution Error: {e}")
        print("\n-------------------------------------------------------")
        print(f"Composio Action Note: {e}")
        print("If Composio prompts for Gmail authorization, visit:")
        print("https://app.composio.dev/apps -> Gmail -> Click Connect")
        print("-------------------------------------------------------\n")
        return None

if __name__ == "__main__":
    email = None
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        email = os.getenv("TEST_EMAIL")
        
    if not email:
        print("Usage: python send_real_test.py <recipient_email>")
        print("Or set TEST_EMAIL environment variable.")
        sys.exit(1)
        
    send_real_test_email(email)
