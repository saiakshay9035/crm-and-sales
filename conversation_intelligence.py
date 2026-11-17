"""
Agent 8: Conversation Intelligence Agent
Processes incoming emails from Gmail, Microsoft Graph, and Inbound Webhooks.
Performs thread matching, idempotency enforcement, deterministic unsubscribe safety,
and structured intent classification.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import database
from events import emit_event, SDRPlatformEvent

logger = logging.getLogger("conversation_intelligence")

# 11 Required Classification Intents
VALID_INTENTS = {
    "INTERESTED",
    "MEETING_REQUESTED",
    "REQUEST_INFORMATION",
    "OBJECTION",
    "FOLLOW_UP_LATER",
    "NOT_INTERESTED",
    "WRONG_CONTACT",
    "REFERRAL",
    "OUT_OF_OFFICE",
    "UNSUBSCRIBE",
    "UNKNOWN"
}

# Strict deterministic keywords that MUST trigger UNSUBSCRIBE immediately
UNSUBSCRIBE_REGEX = re.compile(
    r"\b(unsubscribe|opt[\s-]?out|remove\s+me|take\s+me\s+off|stop\s+emailing|do\s+not\s+contact|leave\s+me\s+alone)\b",
    re.IGNORECASE
)

# Out-of-office automated reply pattern
OUT_OF_OFFICE_REGEX = re.compile(
    r"\b(out\s+of\s+office|away\s+from\s+(the\s+)?office|on\s+(annual\s+)?leave|vacation|auto[\s-]?reply|automatic\s+reply)\b",
    re.IGNORECASE
)

@dataclass
class ReplyClassification:
    intent: str
    confidence_score: float
    evidence_text: str
    recommended_action: str
    should_pause_campaign: bool
    requires_human_approval: bool

    def to_dict(self) -> dict:
        return asdict(self)


class ConversationIntelligenceAgent:
    """
    Inbound Email Listener, Thread Matcher & Reply Classifier.
    """

    def __init__(self, provider_model: str = "fast"):
        self.provider_model = provider_model

    def match_thread(
        self,
        sender_email: str,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references_header: Optional[str] = None,
        org_id: Optional[str] = None
    ) -> Tuple[Optional[dict], Optional[dict]]:
        """
        Matches an incoming email to existing conversation and lead.
        1. Checks in_reply_to and references against existing message_id headers.
        2. Fallback: matches by normalized sender_email in leads table.
        """
        clean_email = sender_email.strip().lower()

        with database.get_connection() as conn:
            # 1. Match by In-Reply-To or References Header
            target_headers = []
            if in_reply_to:
                clean_ref = in_reply_to.strip("<> ")
                target_headers.extend([in_reply_to.strip(), clean_ref, f"<{clean_ref}>"])
            if references_header:
                for ref in references_header.split():
                    clean_ref = ref.strip("<> ")
                    target_headers.extend([ref.strip(), clean_ref, f"<{clean_ref}>"])

            for header in target_headers:
                if not header:
                    continue
                cur = conn.execute(
                    "SELECT conversation_id, org_id FROM conversation_messages WHERE message_id = ? LIMIT 1",
                    (header,)
                )
                msg_row = cur.fetchone()
                if msg_row:
                    conv_id = msg_row["conversation_id"]
                    found_org = msg_row["org_id"]
                    conv = database.get_conversation(conv_id, org_id=found_org)
                    if conv:
                        lead = database.get_lead_by_id(conv["lead_id"])
                        return conv, lead

            # 2. Match by Sender Email in Leads Table
            if org_id:
                cur = conn.execute(
                    "SELECT * FROM leads WHERE lower(email) = ? LIMIT 1",
                    (clean_email,)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM leads WHERE lower(email) = ? LIMIT 1",
                    (clean_email,)
                )
            lead_row = cur.fetchone()
            if lead_row:
                lead = dict(lead_row)
                target_org = org_id or "org_default"
                conv = database.create_or_get_conversation(
                    org_id=target_org,
                    lead_id=lead["id"],
                    subject=f"Outreach to {lead.get('company_name', clean_email)}"
                )
                return conv, lead

        return None, None

    def classify_reply(self, body_text: str, subject: str = "") -> ReplyClassification:
        """
        Classifies incoming reply using deterministic compliance rules first,
        followed by high-accuracy heuristic / structured classification.
        """
        full_text = f"{subject}\n{body_text}".strip()
        full_lower = full_text.lower()

        # RULE 1: STRICT MANDATORY UNSUBSCRIBE SAFETY
        # An explicit unsubscribe request CAN NEVER be overridden by an LLM classification
        unsub_match = UNSUBSCRIBE_REGEX.search(full_lower)
        if unsub_match:
            snippet = unsub_match.group(0)
            return ReplyClassification(
                intent="UNSUBSCRIBE",
                confidence_score=1.0,
                evidence_text=f"Explicit unsubscribe keyword detected: '{snippet}'",
                recommended_action="Permanently stop all campaigns, add to suppression list.",
                should_pause_campaign=True,
                requires_human_approval=False
            )

        # RULE 2: OUT OF OFFICE DETECTION
        ooo_match = OUT_OF_OFFICE_REGEX.search(full_lower)
        if ooo_match:
            return ReplyClassification(
                intent="OUT_OF_OFFICE",
                confidence_score=0.95,
                evidence_text=f"Auto-responder phrase detected: '{ooo_match.group(0)}'",
                recommended_action="Pause campaign temporarily; retry after return date.",
                should_pause_campaign=True,
                requires_human_approval=False
            )

        # RULE 3: NOT INTERESTED / HARD PASS (Evaluated before positive keywords to prevent substring misclassifications)
        not_interested_keywords = ["not interested", "no thank you", "no thanks", "pass on this", "not looking", "please pass"]
        for kw in not_interested_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="NOT_INTERESTED",
                    confidence_score=0.92,
                    evidence_text=f"Disinterest signal: '{kw}'",
                    recommended_action="Mark lead disqualified and cease outreach.",
                    should_pause_campaign=True,
                    requires_human_approval=False
                )

        # RULE 4: MEETING REQUESTED / CALENDAR
        meeting_keywords = [
            "schedule a call", "book a time", "calendar link", "available next week",
            "let's chat tuesday", "open for a call", "send invite", "google meet", "zoom link",
            "discuss this over a call", "discuss over a call", "over a call", "discuss this",
            "jump on a call", "have a call", "set up a call"
        ]
        for kw in meeting_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="MEETING_REQUESTED",
                    confidence_score=0.92,
                    evidence_text=f"Prospect requested call/meeting: '{kw}'",
                    recommended_action="Generate meeting slot proposal and prepare calendar booking.",
                    should_pause_campaign=True,
                    requires_human_approval=False
                )

        # RULE 5: INTERESTED / POSITIVE RESPONSE
        interested_keywords = ["interested", "sounds interesting", "would love to learn more", "tell me more", "share more details", "pricing deck", "send over deck", "send info"]
        for kw in interested_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="INTERESTED",
                    confidence_score=0.90,
                    evidence_text=f"Positive intent signal detected: '{kw}'",
                    recommended_action="Draft customized qualification response answering their questions.",
                    should_pause_campaign=True,
                    requires_human_approval=True
                )

        # RULE 6: REQUEST FOR INFORMATION
        info_keywords = ["how does this work", "how much does it cost", "what is your pricing", "case study", "sample work"]
        for kw in info_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="REQUEST_INFORMATION",
                    confidence_score=0.88,
                    evidence_text=f"Inquiry request detected: '{kw}'",
                    recommended_action="Draft informative response highlighting verified capabilities.",
                    should_pause_campaign=True,
                    requires_human_approval=True
                )

        # RULE 7: OBJECTION / SKEPTICISM
        objection_keywords = ["not right now", "no budget", "we already use", "we have an in-house team", "too expensive"]
        for kw in objection_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="OBJECTION",
                    confidence_score=0.85,
                    evidence_text=f"Sales objection detected: '{kw}'",
                    recommended_action="Log objection and prepare value-reframing response.",
                    should_pause_campaign=True,
                    requires_human_approval=True
                )

        # RULE 8: FOLLOW UP LATER
        later_keywords = ["reach back in", "next quarter", "circle back in q", "busy right now", "ping me in a few months"]
        for kw in later_keywords:
            if kw in full_lower:
                return ReplyClassification(
                    intent="FOLLOW_UP_LATER",
                    confidence_score=0.90,
                    evidence_text=f"Timing deferral detected: '{kw}'",
                    recommended_action="Schedule follow-up reminder for the requested future timeframe.",
                    should_pause_campaign=True,
                    requires_human_approval=False
                )

        # RULE 9: WRONG CONTACT / REFERRAL
        if any(k in full_lower for k in ["not the right person", "wrong person", "reach out to", "talk to my colleague", "contact our cto"]):
            return ReplyClassification(
                intent="REFERRAL" if ("reach out to" in full_lower or "talk to" in full_lower) else "WRONG_CONTACT",
                confidence_score=0.85,
                evidence_text="Re-routing or alternative contact suggested.",
                recommended_action="Update decision maker records with referred contact info.",
                should_pause_campaign=True,
                requires_human_approval=True
            )

        # Fallback UNKNOWN
        return ReplyClassification(
            intent="UNKNOWN",
            confidence_score=0.50,
            evidence_text=body_text[:100],
            recommended_action="Route to human sales representative for manual review.",
            should_pause_campaign=True,
            requires_human_approval=True
        )

    def process_inbound_email(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references_header: Optional[str] = None,
        provider: str = "WEBHOOK",
        org_id: str = "org_default",
        raw_payload: Optional[dict] = None
    ) -> dict:
        """
        Complete end-to-end inbound email handler:
        1. Checks idempotency
        2. Matches thread / conversation / lead
        3. Persists inbound message
        4. Classifies reply intent
        5. Fires event triggers & pauses sequences
        """
        # Idempotency check: derive key from provider message_id or content hash
        idempotency_key = message_id or f"{sender_email}_{recipient_email}_{hash(body_text)}"
        is_fresh, event_or_status = database.record_inbound_email_event(
            org_id=org_id,
            idempotency_key=idempotency_key,
            provider=provider,
            raw_payload=json.dumps(raw_payload or {"body": body_text[:200]})
        )
        if not is_fresh:
            logger.info(f"[Inbound Listener] Ignored duplicate email event ({idempotency_key})")
            return {"status": "DUPLICATE_IGNORED", "idempotency_key": idempotency_key}

        # Thread Matching
        conv, lead = self.match_thread(
            sender_email=sender_email,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references_header=references_header,
            org_id=org_id
        )

        lead_id = lead["id"] if lead else None
        if not conv:
            # Create orphan conversation record if lead not found in CRM yet
            conv = database.create_or_get_conversation(
                org_id=org_id,
                lead_id="unregistered_prospect",
                subject=subject or f"Inbound from {sender_email}"
            )

        # Store incoming message in conversation history
        saved_msg = database.add_conversation_message(
            org_id=org_id,
            conversation_id=conv["id"],
            direction="INBOUND",
            sender_email=sender_email,
            recipient_email=recipient_email,
            body_text=body_text,
            subject=subject,
            body_html=body_html,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references_header=references_header
        )

        # AI Intent Classification
        classification = self.classify_reply(body_text=body_text, subject=subject)
        
        # Persist classification
        class_id = database.save_reply_classification({
            "org_id": org_id,
            "message_id": saved_msg["id"],
            "conversation_id": conv["id"],
            "intent": classification.intent,
            "confidence_score": classification.confidence_score,
            "evidence_text": classification.evidence_text,
            "recommended_action": classification.recommended_action,
            "should_pause_campaign": classification.should_pause_campaign,
            "requires_human_approval": classification.requires_human_approval
        })

        # Event-driven trigger
        event_payload = {
            "conversation_id": conv["id"],
            "message_id": saved_msg["id"],
            "sender_email": sender_email,
            "intent": classification.intent,
            "confidence_score": classification.confidence_score,
            "evidence_text": classification.evidence_text,
            "reason": f"PAUSED_{classification.intent}"
        }

        if classification.intent == "UNSUBSCRIBE":
            emit_event(org_id, SDRPlatformEvent.UNSUBSCRIBED.value, lead_id=lead_id, payload=event_payload)
            if lead_id:
                database.update_lead_outcome(lead_id, "UNSUBSCRIBED")
        elif classification.intent == "MEETING_REQUESTED":
            emit_event(org_id, SDRPlatformEvent.MEETING_REQUESTED.value, lead_id=lead_id, payload=event_payload)
            if lead_id:
                database.update_lead_outcome(lead_id, "MEETING_REQUESTED")
        else:
            emit_event(org_id, SDRPlatformEvent.EMAIL_REPLIED.value, lead_id=lead_id, payload=event_payload)
            if lead_id:
                database.update_lead_outcome(lead_id, f"REPLIED_{classification.intent}")

        emit_event(org_id, SDRPlatformEvent.REPLY_CLASSIFIED.value, lead_id=lead_id, payload=event_payload)

        return {
            "status": "PROCESSED",
            "conversation_id": conv["id"],
            "message_id": saved_msg["id"],
            "classification_id": class_id,
            "classification": classification.to_dict(),
            "lead_id": lead_id
        }


# Global instance
conversation_agent = ConversationIntelligenceAgent()
