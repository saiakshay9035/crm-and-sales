"""
Event-Driven Architecture for Autonomous AI SDR Platform.
Provides reliable, idempotent event recording and cascade handlers.
"""

from enum import Enum
import logging
from typing import Callable, Dict, List, Optional
import database

logger = logging.getLogger("events")

class SDRPlatformEvent(str, Enum):
    PROSPECT_DISCOVERED = "PROSPECT_DISCOVERED"
    CONTACT_VERIFIED = "CONTACT_VERIFIED"
    EMAIL_SENT = "EMAIL_SENT"
    EMAIL_BOUNCED = "EMAIL_BOUNCED"
    EMAIL_REPLIED = "EMAIL_REPLIED"
    REPLY_CLASSIFIED = "REPLY_CLASSIFIED"
    CAMPAIGN_PAUSED = "CAMPAIGN_PAUSED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    MEETING_REQUESTED = "MEETING_REQUESTED"
    MEETING_BOOKED = "MEETING_BOOKED"
    UNSUBSCRIBED = "UNSUBSCRIBED"

# Event listener registry
_EVENT_LISTENERS: Dict[str, List[Callable]] = {}

def register_listener(event_type: str, handler: Callable):
    """Registers a listener for an event type."""
    if event_type not in _EVENT_LISTENERS:
        _EVENT_LISTENERS[event_type] = []
    _EVENT_LISTENERS[event_type].append(handler)

def emit_event(
    org_id: str,
    event_type: str,
    lead_id: Optional[str] = None,
    payload: Optional[dict] = None,
    idempotency_key: Optional[str] = None
) -> bool:
    """
    Persists an event in agent_execution_events and fires all registered handlers.
    Strictly deduplicates against idempotency_key.
    """
    success = database.record_agent_event(
        org_id=org_id,
        event_type=event_type,
        lead_id=lead_id,
        payload=payload or {},
        idempotency_key=idempotency_key
    )
    if not success:
        logger.info(f"[Events] Suppressed duplicate event: {idempotency_key}")
        return False

    logger.info(f"[Event Emitted] org={org_id} type={event_type} lead={lead_id}")

    # Invoke registered listeners
    handlers = _EVENT_LISTENERS.get(event_type, [])
    for handler in handlers:
        try:
            handler(org_id=org_id, lead_id=lead_id, payload=payload or {})
        except Exception as e:
            logger.error(f"[Event Handler Error] {event_type} -> {e}")

    return True

# --- Default Built-in Cascade Handlers ---

def _on_email_replied_or_unsubscribed(org_id: str, lead_id: Optional[str], payload: dict):
    """Automatically pauses any active outbound email sequences for this lead."""
    if not lead_id:
        return
    reason = payload.get("reason", "PAUSED_REPLIED")
    paused = database.pause_all_sequences_for_lead(org_id, lead_id, reason=reason)
    if paused:
        logger.info(f"[Sequence Control] Paused {paused} active sequence(s) for lead {lead_id} (Reason: {reason})")

def _on_email_bounced(org_id: str, lead_id: Optional[str], payload: dict):
    """Marks lead deliverability as BOUNCED and pauses sequences."""
    if not lead_id:
        return
    database.pause_all_sequences_for_lead(org_id, lead_id, reason="PAUSED_BOUNCED")
    database.update_lead_outcome(lead_id, "BOUNCED")

def _on_meeting_booked(org_id: str, lead_id: Optional[str], payload: dict):
    if not lead_id:
        return
    database.pause_all_sequences_for_lead(org_id, lead_id, reason="PAUSED_MEETING_BOOKED")
    database.update_lead_outcome(lead_id, "MEETING_BOOKED")

# Register core cascade handlers
register_listener(SDRPlatformEvent.EMAIL_REPLIED.value, _on_email_replied_or_unsubscribed)
register_listener(SDRPlatformEvent.MEETING_REQUESTED.value, _on_email_replied_or_unsubscribed)
register_listener(SDRPlatformEvent.UNSUBSCRIBED.value, _on_email_replied_or_unsubscribed)
register_listener(SDRPlatformEvent.EMAIL_BOUNCED.value, _on_email_bounced)
register_listener(SDRPlatformEvent.MEETING_BOOKED.value, _on_meeting_booked)
