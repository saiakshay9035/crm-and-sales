import os
import requests
import json
import logging
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResendEmail")

RESEND_API_KEY = settings.RESEND_API_KEY or os.getenv("RESEND_API_KEY", "")
RECIPIENT_EMAIL = "saiakshay30@gmail.com"

def send_real_email():
    logger.info(f"[Resend API] Sending real test email to {RECIPIENT_EMAIL}...")
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": "onboarding@resend.dev",
        "to": [RECIPIENT_EMAIL],
        "subject": "🚀 Live Test: Autonomous AI Lead & Outreach Agent",
        "html": """
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #6366f1;">🚀 Live Test Successful!</h2>
            <p>Hi Sai Akshay,</p>
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
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"[Resend API] HTTP Status: {response.status_code}")
        logger.info(f"[Resend API] Response: {response.text}")
        
        if response.status_code in [200, 201]:
            print("\n=======================================================")
            print(f"🎉 SUCCESS! REAL EMAIL SENT TO {RECIPIENT_EMAIL}!")
            print("Check your Inbox / Spam folder at saiakshay30@gmail.com right now!")
            print("=======================================================\n")
            return True
        else:
            print(f"Resend Error: {response.text}")
            return False
    except Exception as e:
        logger.error(f"[Resend API] Request Exception: {e}")
        return False

if __name__ == "__main__":
    send_real_email()
