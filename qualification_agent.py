"""
Agent 9: AI Qualification Agent
Performs BANT-based (Budget, Authority, Need, Timeline) prospect qualification.
Strict Anti-Hallucination Policy: Unknown fields MUST remain 'UNKNOWN' — never fabricated.
"""

from dataclasses import dataclass, asdict
import logging
import re
from typing import Dict, List, Optional

import database
from events import emit_event, SDRPlatformEvent

logger = logging.getLogger("qualification_agent")

DECISION_MAKER_TITLES = {
    "founder", "co-founder", "ceo", "cto", "coo", "vp", "vice president", "head of", "director", "partner", "managing partner"
}

@dataclass
class BANTQualificationReport:
    budget: str
    authority: str
    need: str
    timeline: str
    fit_score: int
    qualification_status: str  # QUALIFIED, UNQUALIFIED, IN_PROGRESS, NEEDS_INFO
    summary: str

    def to_dict(self) -> dict:
        return asdict(self)


class AIQualificationAgent:
    """
    Analyzes prospect profile and conversation thread to assess BANT sales readiness.
    """

    def qualify_prospect(
        self,
        lead_id: str,
        conversation_id: Optional[str] = None,
        org_id: str = "org_default"
    ) -> BANTQualificationReport:
        """
        Assesses Budget, Authority, Need, and Timeline from grounded evidence only.
        """
        lead = database.get_lead_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Gather conversation text if conversation_id provided
        messages = []
        if conversation_id:
            messages = database.get_conversation_messages(conversation_id, org_id=org_id)

        conv_text = " ".join([m.get("body_text", "") for m in messages]).lower()
        title = (lead.get("founder_title") or "").lower()

        # 1. Authority Assessment
        authority = "UNKNOWN"
        if any(d in title for d in DECISION_MAKER_TITLES):
            authority = f"HIGH (Decision Maker: {lead.get('founder_title')})"
        elif "i make the call" in conv_text or "i am the owner" in conv_text:
            authority = "HIGH (Confirmed Buyer)"
        elif "not the right person" in conv_text or "need to ask my boss" in conv_text:
            authority = "LOW (Requires Escalation)"

        # 2. Budget Assessment (Never assume or fabricate budget)
        budget = "UNKNOWN"
        budget_match = re.search(r"(\$[\d,]+|\d+k\b|budget\s+is\s+approved|budget\s+of\s+[\$\d,]+)", conv_text)
        if budget_match:
            budget = f"CONFIRMED ({budget_match.group(0)})"
        elif "have budget" in conv_text or "funded" in conv_text:
            budget = "VERIFIED_BUDGET_AVAILABLE"
        elif "no budget" in conv_text or "cannot afford" in conv_text:
            budget = "DISQUALIFIED_NO_BUDGET"

        # 3. Need Assessment (Derived strictly from verified intelligence or conversation)
        need = "UNKNOWN"
        ev_items = database.get_lead_evidence(lead_id)
        if "pricing" in conv_text or "how does it work" in conv_text or "need help with" in conv_text:
            need = "ACTIVE_INTEREST (Inquired about pricing and workflow)"
        elif ev_items:
            # Verified buying signals from company discovery
            proven_signals = [e.get("statement") for e in ev_items if e.get("signal_type") in ("HIRING", "FUNDING", "BUYING_TRIGGER")]
            if proven_signals:
                need = f"IDENTIFIED_FROM_EVIDENCE ({proven_signals[0]})"
        
        # 4. Timeline Assessment
        timeline = "UNKNOWN"
        if any(t in conv_text for t in ["asap", "immediately", "this month", "next week", "now"]):
            timeline = "URGENT (Immediate / Next 30 Days)"
        elif any(t in conv_text for t in ["next quarter", "q1", "q2", "q3", "q4", "in a few months"]):
            timeline = "MEDIUM (Next Quarter)"
        elif "next year" in conv_text or "later" in conv_text:
            timeline = "LONG_TERM (> 6 Months)"

        # Calculate Fit Score based on verified parameters
        score = 0
        if "HIGH" in authority:
            score += 35
        elif authority != "UNKNOWN":
            score += 15

        if "CONFIRMED" in budget or "VERIFIED" in budget:
            score += 25
        elif budget == "UNKNOWN":
            score += 10  # Neutral early stage
        elif "NO_BUDGET" in budget:
            score -= 30

        if "ACTIVE" in need or "IDENTIFIED" in need:
            score += 25
        
        if "URGENT" in timeline:
            score += 15
        elif "MEDIUM" in timeline:
            score += 10

        # Determine Qualification Status
        if score >= 65 and "NO_BUDGET" not in budget:
            status = "QUALIFIED"
        elif "NO_BUDGET" in budget or authority == "LOW (Requires Escalation)":
            status = "UNQUALIFIED"
        elif score >= 40:
            status = "IN_PROGRESS"
        else:
            status = "NEEDS_INFO"

        summary = f"BANT Assessment: Authority={authority}, Budget={budget}, Need={need}, Timeline={timeline}. Fit Score: {score}/100."

        report = BANTQualificationReport(
            budget=budget,
            authority=authority,
            need=need,
            timeline=timeline,
            fit_score=score,
            qualification_status=status,
            summary=summary
        )

        # Persist record in database
        database.save_qualification_record({
            "org_id": org_id,
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "budget": report.budget,
            "authority": report.authority,
            "need": report.need,
            "timeline": report.timeline,
            "fit_score": report.fit_score,
            "qualification_status": report.qualification_status,
            "summary": report.summary
        })

        if status == "QUALIFIED":
            emit_event(
                org_id=org_id,
                event_type=SDRPlatformEvent.LEAD_QUALIFIED.value,
                lead_id=lead_id,
                payload=report.to_dict()
            )

        return report


# Global instance
qualification_agent = AIQualificationAgent()
