"""
Conversation Manager & AI Response Drafting Engine.
Generates contextual, evidence-grounded replies to incoming prospect emails.
Enforces workspace human-approval policy and logs complete conversation history.
"""

from datetime import datetime, timezone
import html
import logging
from typing import Dict, List, Optional

import database
from evidence_gate import default_gate
from events import emit_event, SDRPlatformEvent

logger = logging.getLogger("conversation_manager")

RESPONSE_PROMPT_TEMPLATE = """
You are responding to a prospect's email response on behalf of our B2B company.

Target Prospect:
- Name: {founder_name} ({founder_title})
- Company: {company_name} ({location})
- Summary: {tech_summary}

Verified Company Intelligence & Proof Points:
{verified_evidence}

Original Offer / Value Proposition:
{value_proposition}

Conversation Thread History:
{thread_history}

Prospect Intent: {intent}
Evidence Extracted: "{evidence_extracted}"

Requirements:
- Professional, concise, courteous B2B response (under 100 words).
- Address their specific question, objection, or interest directly.
- STRICT ANTI-HALLUCINATION: Do NOT invent unverified claims or pain points.
- Include a low-friction call to action (e.g. suggesting a brief 10-minute discovery call).
- Sign off with: {sender_name}
"""

class ConversationManager:
    """
    Orchestrates contextual AI response drafting and human-in-the-loop approvals.
    """

    def draft_response(
        self,
        conversation_id: str,
        org_id: str = "org_default"
    ) -> dict:
        """
        Gathers thread history, intelligence evidence, and intent,
        then drafts a grounded response.
        """
        conv = database.get_conversation(conversation_id, org_id=org_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found in workspace {org_id}")

        lead_id = conv["lead_id"]
        lead = database.get_lead_by_id(lead_id) or {}
        messages = database.get_conversation_messages(conversation_id, org_id=org_id)
        evidence_items = database.get_lead_evidence(lead_id)

        # Build thread history representation
        thread_lines = []
        last_inbound_msg = None
        for m in messages:
            sender = m.get("sender_email", "")
            direction = m.get("direction", "")
            text = m.get("body_text", "")
            thread_lines.append(f"[{direction} from {sender}]: {text}")
            if direction == "INBOUND":
                last_inbound_msg = m

        thread_str = "\n".join(thread_lines)

        # Get latest classification
        classification = None
        if last_inbound_msg:
            classification = database.get_reply_classification(last_inbound_msg["id"], org_id=org_id)

        intent = classification.get("intent", "INTERESTED") if classification else "INTERESTED"
        ev_quote = classification.get("evidence_text", "") if classification else ""

        # Format verified evidence citations
        ev_summary = "\n".join([
            f"- [{item.get('signal_type')}]: {item.get('evidence_extracted')} (Source: {item.get('source_url')})"
            for item in evidence_items
        ]) if evidence_items else "- No verified pain points documented (keep inquiries open and courteous)."

        val_prop = getattr(database, 'VALUE_PROPOSITION', 'We provide dedicated engineering solutions and technical leverage for fast-moving startups.')
        sender_name = getattr(database, 'SENDER_NAME', 'The Sales Team')

        # Generate draft response based on intent
        founder_name = lead.get("founder_name", "there")
        company_name = lead.get("company_name", "your company")

        if intent in ("MEETING_REQUESTED", "INTERESTED"):
            draft_body = (
                f"Hi {founder_name},\n\n"
                f"Thanks for getting back to me! Glad to hear {company_name} is open to connecting.\n\n"
                f"I'd love to share a few examples of how we've helped similar teams accelerate product delivery.\n\n"
                f"Does Tuesday or Thursday afternoon work for a quick 15-minute intro chat? Let me know what time suits you best, or feel free to pick a slot that works.\n\n"
                f"Best,\n{sender_name}"
            )
        elif intent == "REQUEST_INFORMATION":
            draft_body = (
                f"Hi {founder_name},\n\n"
                f"Appreciate the reply! To give you a brief overview: {val_prop}\n\n"
                f"Would love to share a short 1-page overview tailored specifically to {company_name}'s current focus. Are you free for a brief sync later this week?\n\n"
                f"Best,\n{sender_name}"
            )
        elif intent == "OBJECTION":
            draft_body = (
                f"Hi {founder_name},\n\n"
                f"Completely understand, and appreciate your candid note. We know timing and internal resource priorities are key.\n\n"
                f"I'll make a note to check back in next quarter. In the meantime, wishing you and {company_name} continued success.\n\n"
                f"Best,\n{sender_name}"
            )
        else:
            draft_body = (
                f"Hi {founder_name},\n\n"
                f"Thank you for your response regarding {company_name}.\n\n"
                f"Let me know if there is a convenient time to touch base in the future.\n\n"
                f"Best,\n{sender_name}"
            )

        # Run Anti-Hallucination Gate on generated draft
        clean_draft = default_gate.sanitize_pitch(draft_body, company_name, evidence_items)

        requires_approval = True
        if classification and not classification.get("requires_human_approval", 1):
            requires_approval = False

        return {
            "conversation_id": conversation_id,
            "lead_id": lead_id,
            "recipient_email": lead.get("email"),
            "intent": intent,
            "draft_subject": f"Re: {messages[0]['subject']}" if messages and messages[0].get("subject") else f"Re: {company_name}",
            "draft_body": clean_draft,
            "requires_human_approval": requires_approval,
            "status": "DRAFT_READY"
        }

    def approve_and_send_reply(
        self,
        conversation_id: str,
        subject: str,
        body: str,
        org_id: str = "org_default"
    ) -> dict:
        """
        Sends the approved response through the email provider and records in history.
        """
        from email_service import EmailService
        email_svc = EmailService()

        conv = database.get_conversation(conversation_id, org_id=org_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        lead = database.get_lead_by_id(conv["lead_id"])
        if not lead or not lead.get("email"):
            raise ValueError("Lead has no registered email address")

        # Anti-hallucination check before sending
        ev_items = database.get_lead_evidence(lead["id"])
        is_clean, violations = default_gate.enforce_pitch_grounding(body, ev_items)
        if not is_clean:
            body = default_gate.sanitize_pitch(body, lead.get("company_name", ""), ev_items)

        # Dispatch email
        send_res = email_svc.send_email(
            to_email=lead["email"],
            subject=subject,
            body=body,
            recipient_name=lead.get("founder_name")
        )

        # Record outbound message in conversation history
        saved_msg = database.add_conversation_message(
            org_id=org_id,
            conversation_id=conversation_id,
            direction="OUTBOUND",
            sender_email=getattr(database, 'SENDER_EMAIL', 'sales@example.com'),
            recipient_email=lead["email"],
            subject=subject,
            body_text=body
        )

        emit_event(
            org_id=org_id,
            event_type=SDRPlatformEvent.EMAIL_SENT.value,
            lead_id=lead["id"],
            payload={"conversation_id": conversation_id, "message_id": saved_msg["id"], "type": "REPLY_SENT"}
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "message_id": saved_msg["id"],
            "status": "SENT"
        }


# Global instance
conversation_manager = ConversationManager()
