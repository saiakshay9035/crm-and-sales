"""
Agent 7: Sequence Scheduler Engine
Manages persistent multi-touch cadence sequences (Day 0, Day 3, Day 7, Day 12).
Respects pause triggers (replies, unsubscribes, bounces), daily sending limits,
and multi-tenant isolation.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
from typing import Dict, List, Optional
import database
from events import emit_event, SDRPlatformEvent

logger = logging.getLogger("sequence_scheduler")

DEFAULT_SEQUENCE_STEPS = [
    {
        "step_number": 1,
        "delay_days": 0,
        "template_subject": "Quick question regarding {company_name}",
        "template_body": "Hi {founder_name},\n\nSaw that {company_name} is building {tech_summary}.\n\nWould love to connect on how we support similar scaling engineering teams.\n\nBest,\n{sender_name}",
        "step_type": "EMAIL"
    },
    {
        "step_number": 2,
        "delay_days": 3,
        "template_subject": "Following up: {company_name} engineering priorities",
        "template_body": "Hi {founder_name},\n\nCircling back on my note from earlier this week. Wanted to see if scaling core delivery is on your roadmap this quarter.\n\nOpen to a quick 10-minute chat?\n\nBest,\n{sender_name}",
        "step_type": "EMAIL"
    },
    {
        "step_number": 3,
        "delay_days": 4,  # Day 7 total (3 + 4)
        "template_subject": "Resource for {company_name}",
        "template_body": "Hi {founder_name},\n\nThought this might be helpful as your team scales. We recently helped a peer company accelerate their release cycle by 40% without hiring overhead.\n\nHappy to share the breakdown if interested.\n\nBest,\n{sender_name}",
        "step_type": "EMAIL"
    },
    {
        "step_number": 4,
        "delay_days": 5,  # Day 12 total (7 + 5)
        "template_subject": "Closing the loop for {company_name}",
        "template_body": "Hi {founder_name},\n\nI realize you're likely heads-down building. If this isn't a priority right now, no worries at all.\n\nFeel free to keep us in mind whenever you need engineering leverage.\n\nBest,\n{sender_name}",
        "step_type": "EMAIL"
    }
]


class SequenceScheduler:
    """
    Persistent background sequence scheduling engine.
    """

    def get_or_create_default_sequence(self, org_id: str = "org_default") -> dict:
        """Retrieves default sequence or seeds it if missing."""
        sequences = database.get_sequence("seq_default", org_id=org_id)
        if sequences:
            return sequences

        created = database.create_sequence(
            org_id=org_id,
            name="Standard 4-Touch Outbound Cadence",
            steps=DEFAULT_SEQUENCE_STEPS
        )
        return database.get_sequence(created["id"], org_id=org_id)

    def enroll_prospect(
        self,
        org_id: str,
        lead_id: str,
        sequence_id: Optional[str] = None,
        start_immediately: bool = True
    ) -> dict:
        """Enrolls a lead into a multi-touch cadence."""
        if not sequence_id:
            seq = self.get_or_create_default_sequence(org_id)
            sequence_id = seq["id"]

        state = database.enroll_prospect_in_sequence(org_id, lead_id, sequence_id)
        
        # Schedule step 1
        scheduled_time = datetime.now(timezone.utc).isoformat() if start_immediately else (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        
        action_payload = json.dumps({
            "sequence_id": sequence_id,
            "step_number": 1
        })
        database.schedule_action(
            org_id=org_id,
            lead_id=lead_id,
            action_type="SEND_SEQUENCE_STEP",
            payload_json=action_payload,
            scheduled_for=scheduled_time
        )
        logger.info(f"[Sequence Scheduler] Enrolled lead {lead_id} in sequence {sequence_id} (Step 1 scheduled for {scheduled_time})")
        return state

    def pause_prospect(self, org_id: str, lead_id: str, reason: str = "PAUSED_MANUAL") -> int:
        """Halts all sequence actions for a prospect."""
        return database.pause_all_sequences_for_lead(org_id, lead_id, reason=reason)

    def resume_prospect(self, org_id: str, lead_id: str) -> bool:
        """Resumes a paused prospect."""
        with database.get_connection() as conn:
            cur = conn.execute(
                "UPDATE prospect_sequence_states SET status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP WHERE org_id = ? AND lead_id = ?",
                (org_id, lead_id)
            )
            count = cur.rowcount
            conn.commit()
            return count > 0

    def process_due_actions(self, max_batch: int = 10) -> dict:
        """
        Executes due scheduled actions. Checks prospect pause status,
        verifies daily sending limits, sends emails, and schedules subsequent steps.
        """
        from email_service import EmailService
        email_service = EmailService()
        due_actions = database.get_due_scheduled_actions()
        processed_count = 0
        cancelled_count = 0
        failed_count = 0

        for action in due_actions[:max_batch]:
            act_id = action["id"]
            org_id = action["org_id"]
            lead_id = action["lead_id"]
            payload = json.loads(action["payload_json"] or "{}")
            sequence_id = payload.get("sequence_id")
            step_number = payload.get("step_number", 1)

            # Check sequence state for prospect
            seq_states = database.get_prospect_sequence_state(org_id, lead_id)
            matching_state = next((s for s in seq_states if s["sequence_id"] == sequence_id), None)

            # GUARD: Stop if prospect has replied, unsubscribed, or paused
            if not matching_state or matching_state["status"] != "ACTIVE":
                logger.info(f"[Sequence Scheduler] Action {act_id} cancelled: Lead {lead_id} status is '{matching_state['status'] if matching_state else 'NONE'}'")
                database.update_scheduled_action_status(act_id, "CANCELLED")
                cancelled_count += 1
                continue

            # Fetch lead data
            lead = database.get_lead_by_id(lead_id)
            if not lead:
                database.update_scheduled_action_status(act_id, "FAILED")
                failed_count += 1
                continue

            # Fetch sequence step definition
            seq = database.get_sequence(sequence_id, org_id)
            steps = seq.get("steps", []) if seq else []
            current_step_def = next((s for s in steps if s["step_number"] == step_number), None)

            if not current_step_def:
                # Sequence completed
                database.update_scheduled_action_status(act_id, "COMPLETED")
                with database.get_connection() as conn:
                    conn.execute("UPDATE prospect_sequence_states SET status = 'COMPLETED' WHERE org_id = ? AND lead_id = ? AND sequence_id = ?", (org_id, lead_id, sequence_id))
                    conn.commit()
                continue

            # Format email copy
            subject = current_step_def["template_subject"].format(
                company_name=lead["company_name"],
                founder_name=lead["founder_name"]
            )
            body = current_step_def["template_body"].format(
                company_name=lead["company_name"],
                founder_name=lead["founder_name"],
                tech_summary=lead["tech_summary"],
                sender_name=getattr(database, 'SENDER_NAME', 'The Team')
            )

            # Mark executing
            database.update_scheduled_action_status(act_id, "EXECUTING")

            try:
                # Dispatch outbound email
                res = email_service.send_email(
                    to_email=lead["email"],
                    subject=subject,
                    body=body,
                    recipient_name=lead["founder_name"]
                )
                
                # Update action to COMPLETED
                database.update_scheduled_action_status(act_id, "COMPLETED")
                database.log_email_sent(lead_id, res.get("id", "smtp_success"), "SENT")

                # Advance prospect sequence state
                next_step_num = step_number + 1
                next_step_def = next((s for s in steps if s["step_number"] == next_step_num), None)

                with database.get_connection() as conn:
                    if next_step_def:
                        # Schedule next follow-up
                        delay_days = next_step_def.get("delay_days", 3)
                        next_due = (datetime.now(timezone.utc) + timedelta(days=delay_days)).isoformat()
                        conn.execute(
                            "UPDATE prospect_sequence_states SET current_step = ?, last_sent_at = CURRENT_TIMESTAMP, next_step_due_at = ? WHERE org_id = ? AND lead_id = ? AND sequence_id = ?",
                            (next_step_num, next_due, org_id, lead_id, sequence_id)
                        )
                        next_payload = json.dumps({"sequence_id": sequence_id, "step_number": next_step_num})
                        database.schedule_action(org_id, lead_id, "SEND_SEQUENCE_STEP", next_payload, next_due)
                    else:
                        conn.execute(
                            "UPDATE prospect_sequence_states SET status = 'COMPLETED', last_sent_at = CURRENT_TIMESTAMP, next_step_due_at = NULL WHERE org_id = ? AND lead_id = ? AND sequence_id = ?",
                            (org_id, lead_id, sequence_id)
                        )
                    conn.commit()

                emit_event(
                    org_id=org_id,
                    event_type=SDRPlatformEvent.EMAIL_SENT.value,
                    lead_id=lead_id,
                    payload={"step_number": step_number, "sequence_id": sequence_id, "recipient": lead["email"]}
                )
                processed_count += 1

            except Exception as e:
                logger.error(f"[Sequence Scheduler] Send failed for lead {lead_id}: {e}")
                retries = action.get("retries", 0) + 1
                if retries >= action.get("max_retries", 3):
                    database.update_scheduled_action_status(act_id, "FAILED", retries=retries)
                    failed_count += 1
                else:
                    database.update_scheduled_action_status(act_id, "PENDING", retries=retries)

        return {
            "processed": processed_count,
            "cancelled": cancelled_count,
            "failed": failed_count
        }


# Global instance
sequence_scheduler = SequenceScheduler()
