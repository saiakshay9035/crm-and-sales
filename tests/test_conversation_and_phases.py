import pytest
from datetime import datetime, timezone, timedelta
import json
import uuid

import database
from events import emit_event, SDRPlatformEvent
from conversation_intelligence import conversation_agent, ConversationIntelligenceAgent
from sequence_scheduler import sequence_scheduler, SequenceScheduler
from conversation_manager import conversation_manager
from qualification_agent import qualification_agent
from calendar_booking import calendar_agent


@pytest.fixture
def test_lead():
    unique_suffix = str(uuid.uuid4())[:8]
    lead_id = f"test_lead_{unique_suffix}"
    lead_dict = {
        "id": lead_id,
        "company_name": f"Acme Innovations {unique_suffix}",
        "domain": f"acme_{unique_suffix}.io",
        "location": "San Francisco, US",
        "founder_name": "Elena Rostova",
        "founder_title": "Founder & CEO",
        "email": f"elena_{unique_suffix}@acme.io",
        "tech_summary": "High-throughput cloud inference engine.",
        "deliverability_score": 95,
        "deliverability_status": "IDENTITY_VERIFIED_CURRENT",
        "linkedin_url": f"https://www.linkedin.com/in/elenarostova_{unique_suffix}",
        "icp_reason": "Pre-seed AI Cloud Startup",
        "status": "DRAFT_REVIEW"
    }
    database.add_lead(lead_dict)
    saved_id = lead_dict["id"]
    yield database.get_lead_by_id(saved_id)
    database.remove_lead(saved_id)


def test_thread_matching_by_email_and_headers(test_lead):
    org_id = "org_default"
    # Create conversation and initial outbound message
    conv = database.create_or_get_conversation(org_id, test_lead["id"], subject="Inquiry on scaling")
    outbound_msg_id = f"<msg-outbound-{uuid.uuid4()}@domain.com>"
    
    database.add_conversation_message(
        org_id=org_id,
        conversation_id=conv["id"],
        direction="OUTBOUND",
        sender_email="sales@sdr.com",
        recipient_email=test_lead["email"],
        subject="Inquiry on scaling",
        body_text="Hi Elena, noticed you are building high-throughput cloud inference.",
        message_id=outbound_msg_id
    )

    # 1. Match by In-Reply-To header
    matched_conv, matched_lead = conversation_agent.match_thread(
        sender_email="unknown_alias@other.com",
        in_reply_to=outbound_msg_id,
        org_id=org_id
    )
    assert matched_conv is not None
    assert matched_conv["id"] == conv["id"]
    assert matched_lead["id"] == test_lead["id"]

    # 2. Fallback match by normalized sender email
    matched_conv2, matched_lead2 = conversation_agent.match_thread(
        sender_email=test_lead["email"].upper(),  # Test case-insensitivity
        org_id=org_id
    )
    assert matched_conv2 is not None
    assert matched_conv2["id"] == conv["id"]


def test_multi_tenant_isolation(test_lead):
    org_a = "org_tenant_alpha"
    org_b = "org_tenant_beta"

    # Seed organizations
    with database._lock, database.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO organizations (id, name) VALUES (?, ?)", (org_a, "Tenant Alpha"))
        conn.execute("INSERT OR IGNORE INTO organizations (id, name) VALUES (?, ?)", (org_b, "Tenant Beta"))
        conn.commit()

    conv_a = database.create_or_get_conversation(org_a, test_lead["id"], subject="Alpha Outreach")
    conv_b = database.create_or_get_conversation(org_b, test_lead["id"], subject="Beta Outreach")

    # Verify Org A cannot access Org B conversation
    assert database.get_conversation(conv_a["id"], org_id=org_b) is None
    assert database.get_conversation(conv_b["id"], org_id=org_a) is None

    # Verify listing isolated per tenant
    list_a = database.list_conversations(org_id=org_a)
    list_b = database.list_conversations(org_id=org_b)
    ids_a = {c["id"] for c in list_a}
    ids_b = {c["id"] for c in list_b}
    assert conv_a["id"] in ids_a
    assert conv_a["id"] not in ids_b


def test_inbound_idempotency_duplicate_suppression(test_lead):
    idempotency_key = f"idemp_{uuid.uuid4()}"
    payload = {
        "sender_email": test_lead["email"],
        "recipient_email": "sales@sdr.com",
        "subject": "Re: scaling",
        "body_text": "Sounds interesting, let's talk next week.",
        "message_id": idempotency_key
    }

    # First delivery: processed
    res1 = conversation_agent.process_inbound_email(
        sender_email=payload["sender_email"],
        recipient_email=payload["recipient_email"],
        subject=payload["subject"],
        body_text=payload["body_text"],
        message_id=payload["message_id"]
    )
    assert res1["status"] == "PROCESSED"

    # Second delivery with identical idempotency_key: suppressed
    res2 = conversation_agent.process_inbound_email(
        sender_email=payload["sender_email"],
        recipient_email=payload["recipient_email"],
        subject=payload["subject"],
        body_text=payload["body_text"],
        message_id=payload["message_id"]
    )
    assert res2["status"] == "DUPLICATE_IGNORED"


def test_reply_classifications_and_intents():
    agent = conversation_agent

    # 1. Interested
    c1 = agent.classify_reply("This sounds very interesting. Would love to learn more and see a demo.")
    assert c1.intent == "INTERESTED"
    assert c1.should_pause_campaign is True

    # 2. Meeting requested
    c2 = agent.classify_reply("Let's schedule a call next Tuesday at 2pm. Send an invite.")
    assert c2.intent == "MEETING_REQUESTED"
    assert c2.should_pause_campaign is True

    # 3. Objection
    c3 = agent.classify_reply("We already use an internal tool for this and have no budget.")
    assert c3.intent == "OBJECTION"

    # 4. Out of Office
    c4 = agent.classify_reply("I am out of office until Monday on annual leave with limited email access.")
    assert c4.intent == "OUT_OF_OFFICE"

    # 5. Not interested
    c5 = agent.classify_reply("Not interested, please pass.")
    assert c5.intent == "NOT_INTERESTED"


def test_strict_deterministic_unsubscribe_safety(test_lead):
    # Ensure that even if the message contains positive words, explicit unsubscribe is NEVER overridden
    tricky_unsub = "This is a great product, but please unsubscribe me immediately and remove me from your list."
    classification = conversation_agent.classify_reply(tricky_unsub)
    
    assert classification.intent == "UNSUBSCRIBE"
    assert classification.confidence_score == 1.0
    assert classification.should_pause_campaign is True

    # Process inbound with unsubscribe
    res = conversation_agent.process_inbound_email(
        sender_email=test_lead["email"],
        recipient_email="sales@sdr.com",
        subject="Re: Question",
        body_text=tricky_unsub,
        message_id=f"unsub_msg_{uuid.uuid4()}"
    )
    assert res["classification"]["intent"] == "UNSUBSCRIBE"

    # Check lead outcome in CRM updated
    updated_lead = database.get_lead_by_id(test_lead["id"])
    assert updated_lead["outcome_status"] == "UNSUBSCRIBED"


def test_sequence_scheduling_and_step_delays(test_lead):
    org_id = "org_default"
    seq = sequence_scheduler.get_or_create_default_sequence(org_id)
    assert len(seq["steps"]) >= 4

    # Enroll prospect
    enrollment = sequence_scheduler.enroll_prospect(org_id, test_lead["id"], seq["id"], start_immediately=True)
    assert enrollment["status"] == "ACTIVE"

    # Check state in DB
    state = database.get_prospect_sequence_state(org_id, test_lead["id"])
    assert len(state) == 1
    assert state[0]["current_step"] == 1


def test_sequence_auto_pause_on_reply(test_lead):
    org_id = "org_default"
    seq = sequence_scheduler.get_or_create_default_sequence(org_id)
    sequence_scheduler.enroll_prospect(org_id, test_lead["id"], seq["id"])

    # Simulate inbound reply arriving
    reply_text = "I saw your note. When can we discuss this over a call?"
    conversation_agent.process_inbound_email(
        sender_email=test_lead["email"],
        recipient_email="sales@sdr.com",
        subject="Re: Outbound",
        body_text=reply_text,
        message_id=f"reply_{uuid.uuid4()}",
        org_id=org_id
    )

    # Verify all sequence states for this prospect are now PAUSED
    state = database.get_prospect_sequence_state(org_id, test_lead["id"])
    assert len(state) == 1
    assert state[0]["status"] == "PAUSED_MEETING_REQUESTED"


def test_ai_response_drafting_and_grounding(test_lead):
    org_id = "org_default"
    conv = database.create_or_get_conversation(org_id, test_lead["id"], subject="Outreach")
    
    # Inbound message
    inbound = database.add_conversation_message(
        org_id=org_id,
        conversation_id=conv["id"],
        direction="INBOUND",
        sender_email=test_lead["email"],
        recipient_email="sales@sdr.com",
        subject="Re: Outreach",
        body_text="Sounds great, what is your pricing and how quickly can we start?"
    )
    database.save_reply_classification({
        "org_id": org_id,
        "message_id": inbound["id"],
        "conversation_id": conv["id"],
        "intent": "REQUEST_INFORMATION",
        "confidence_score": 0.95,
        "evidence_text": "pricing and how quickly can we start"
    })

    # Draft response
    draft = conversation_manager.draft_response(conv["id"], org_id=org_id)
    assert draft["status"] == "DRAFT_READY"
    assert "Elena" in draft["draft_body"] or "Acme" in draft["draft_body"]
    assert draft["requires_human_approval"] is True


def test_bant_qualification_agent(test_lead):
    org_id = "org_default"
    conv = database.create_or_get_conversation(org_id, test_lead["id"])

    # Add message with budget and timeline indicators
    database.add_conversation_message(
        org_id=org_id,
        conversation_id=conv["id"],
        direction="INBOUND",
        sender_email=test_lead["email"],
        recipient_email="sales@sdr.com",
        subject="Re: Info",
        body_text="We have an approved budget of $50,000 for this initiative and want to launch immediately this month."
    )

    report = qualification_agent.qualify_prospect(test_lead["id"], conversation_id=conv["id"], org_id=org_id)
    
    assert "50,000" in report.budget or "VERIFIED" in report.budget
    assert "Decision Maker" in report.authority or "HIGH" in report.authority
    assert "URGENT" in report.timeline or "Immediate" in report.timeline
    assert report.fit_score >= 65
    assert report.qualification_status == "QUALIFIED"

    # Verify recorded in DB
    record = database.get_qualification_record(test_lead["id"], org_id=org_id)
    assert record is not None
    assert record["qualification_status"] == "QUALIFIED"


def test_calendar_booking_enforces_explicit_agreement(test_lead):
    org_id = "org_default"
    slots = calendar_agent.get_available_slots(org_id, days_ahead=3)
    assert len(slots) >= 1
    slot = slots[0]

    # 1. Attempting booking WITHOUT explicit agreement MUST fail
    with pytest.raises(ValueError) as excinfo:
        calendar_agent.book_meeting(
            org_id=org_id,
            lead_id=test_lead["id"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
            title="Discovery Meeting",
            explicit_prospect_agreement=False
        )
    assert "BOOKING REJECTED" in str(excinfo.value)

    # 2. Booking WITH explicit agreement succeeds and pauses outreach
    booking = calendar_agent.book_meeting(
        org_id=org_id,
        lead_id=test_lead["id"],
        start_time=slot["start_time"],
        end_time=slot["end_time"],
        title="Discovery Meeting",
        explicit_prospect_agreement=True
    )
    assert booking["status"] == "CONFIRMED"
    assert booking["explicit_prospect_agreement"] is True

    # Verify CRM outcome updated
    lead = database.get_lead_by_id(test_lead["id"])
    assert lead["outcome_status"] == "MEETING_BOOKED"


def test_event_driven_audit_trail(test_lead):
    org_id = "org_test_audit"
    event_key = f"evt_key_{uuid.uuid4()}"

    emitted = emit_event(
        org_id=org_id,
        event_type=SDRPlatformEvent.CONTACT_VERIFIED.value,
        lead_id=test_lead["id"],
        payload={"verified_by": "DNS_MX"},
        idempotency_key=event_key
    )
    assert emitted is True

    # Duplicate emission suppressed
    dup = emit_event(
        org_id=org_id,
        event_type=SDRPlatformEvent.CONTACT_VERIFIED.value,
        lead_id=test_lead["id"],
        payload={"verified_by": "DNS_MX"},
        idempotency_key=event_key
    )
    assert dup is False

    # Check event history in DB
    events = database.list_agent_events(org_id=org_id, lead_id=test_lead["id"])
    assert len(events) >= 1
    assert events[0]["event_type"] == SDRPlatformEvent.CONTACT_VERIFIED.value
