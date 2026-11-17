import pytest
from datetime import datetime, timezone
import json
import sqlite3
from fastapi.testclient import TestClient

from evidence_gate import AntiHallucinationGate, EvidenceItem, default_gate
import database
from scraper import extract_grounded_evidence, detect_buying_triggers, extract_pain_signals
from enricher import AIProspectEnricher
from dashboard import app

@pytest.fixture
def gate():
    return AntiHallucinationGate(min_confidence=0.65)

@pytest.fixture
def valid_evidence():
    return {
        "source_url": "https://example.com/careers",
        "evidence_extracted": "We are actively hiring senior full-stack engineers to scale our platform.",
        "date_discovered": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.95,
        "signal_type": "HIRING",
        "statement": "Example Corp is actively expanding engineering talent."
    }

def test_valid_evidence_passes_gate(gate, valid_evidence):
    is_valid, reason = gate.validate_evidence(valid_evidence)
    assert is_valid is True
    assert reason == "VALID"

def test_missing_source_url_rejected(gate, valid_evidence):
    invalid = dict(valid_evidence)
    invalid["source_url"] = ""
    is_valid, reason = gate.validate_evidence(invalid)
    assert is_valid is False
    assert "source_url" in reason

def test_invalid_url_scheme_rejected(gate, valid_evidence):
    invalid = dict(valid_evidence)
    invalid["source_url"] = "ftp://not-web.com/file"
    is_valid, reason = gate.validate_evidence(invalid)
    assert is_valid is False
    assert "scheme" in reason

def test_short_or_placeholder_evidence_rejected(gate, valid_evidence):
    invalid_short = dict(valid_evidence)
    invalid_short["evidence_extracted"] = "too short"
    is_valid, reason = gate.validate_evidence(invalid_short)
    assert is_valid is False
    assert "too short" in reason

    invalid_placeholder = dict(valid_evidence)
    invalid_placeholder["evidence_extracted"] = "placeholder"
    is_valid, reason = gate.validate_evidence(invalid_placeholder)
    assert is_valid is False
    assert "placeholder" in reason

def test_invalid_date_rejected(gate, valid_evidence):
    invalid = dict(valid_evidence)
    invalid["date_discovered"] = "not-a-valid-date"
    is_valid, reason = gate.validate_evidence(invalid)
    assert is_valid is False
    assert "timestamp" in reason

def test_confidence_score_boundaries(gate, valid_evidence):
    # Too low
    low = dict(valid_evidence)
    low["confidence_score"] = 0.40
    is_valid, reason = gate.validate_evidence(low)
    assert is_valid is False
    assert "below minimum threshold" in reason

    # Exceeds 1.0
    high = dict(valid_evidence)
    high["confidence_score"] = 1.50
    is_valid, reason = gate.validate_evidence(high)
    assert is_valid is False
    assert "cannot exceed 1.0" in reason

def test_verify_grounded_statement(gate, valid_evidence):
    statement = "Example Corp is scaling engineering hiring for full-stack developers."
    is_grounded, msg = gate.verify_statement(statement, [valid_evidence])
    assert is_grounded is True
    assert msg == "GROUNDED"

def test_reject_hallucinated_pain_point(gate, valid_evidence):
    # Evidence only talks about hiring engineers.
    # Agent tries to invent that they have salary overhead and freelancer management drag!
    statement = "I know your company is suffering from developer salary overhead and freelancer drag."
    is_grounded, msg = gate.verify_statement(statement, [valid_evidence])
    assert is_grounded is False
    assert "HALLUCINATION REJECTED" in msg

def test_pitch_hallucination_detection_and_sanitization(gate, valid_evidence):
    hallucinated_pitch = (
        "Subject: Quick question\n\n"
        "Hi John, noticed you have expensive developers and high salary overhead. "
        "We can cut your costs.\n\nBest,\nSales Team"
    )
    is_clean, violations = gate.enforce_pitch_grounding(hallucinated_pitch, [valid_evidence])
    assert is_clean is False
    assert len(violations) > 0

    sanitized = gate.sanitize_pitch(hallucinated_pitch, "Example Corp", [valid_evidence])
    assert "salary overhead" not in sanitized.lower()
    assert "prioritizing product delivery" in sanitized

def test_scraper_grounded_evidence_extraction():
    sample_text = (
        "Acme AI announced today it raised a $2M seed round from Y Combinator to build its analytics cloud. "
        "We are also hiring senior engineers in San Francisco to join our founding core team."
    )
    evidence = extract_grounded_evidence("Acme AI", "acme.ai", "https://acme.ai/news", sample_text)
    
    assert len(evidence) >= 2
    types = {e["signal_type"] for e in evidence}
    assert "HIRING" in types
    assert "FUNDING" in types

    # Ensure no fabricated pain points were created
    pains = extract_pain_signals("Acme AI", sample_text, source_url="https://acme.ai", domain="acme.ai")
    assert len(pains) == 0  # No pain points in sample text => zero invented pains!

def test_database_evidence_lifecycle():
    lead_id = f"test_ev_{int(datetime.now().timestamp())}"
    lead_data = {
        "id": lead_id,
        "company_name": "Provenance Health",
        "domain": "provenancehealth.org",
        "location": "Boston, US",
        "founder_name": "Sarah Connor",
        "founder_title": "Founder & CEO",
        "email": "sarah@provenancehealth.org",
        "tech_summary": "Healthcare interoperability platform.",
        "deliverability_score": 95,
        "deliverability_status": "IDENTITY_VERIFIED_CURRENT",
        "linkedin_url": "https://www.linkedin.com/in/sarahconnor",
        "icp_reason": "Target HealthTech",
        "evidence": [
            {
                "source_url": "https://provenancehealth.org/press",
                "evidence_extracted": "Provenance Health closed Seed financing led by HealthTech Capital.",
                "date_discovered": datetime.now(timezone.utc).isoformat(),
                "confidence_score": 0.95,
                "signal_type": "FUNDING",
                "statement": "Provenance Health raised seed funding for healthcare interoperability."
            }
        ]
    }
    
    added = database.add_lead(lead_data)
    assert added is True

    # Retrieve evidence from DB
    persisted_id = lead_data["id"]
    records = database.get_lead_evidence(persisted_id)
    assert len(records) >= 1
    rec = records[0]
    assert rec["source_url"] == "https://provenancehealth.org/press"
    assert "Seed financing" in rec["evidence_extracted"]
    assert rec["confidence_score"] == 0.95

    # Test invalid evidence cannot be persisted
    invalid_ev = {
        "source_url": "invalid-url",
        "evidence_extracted": "bad",
        "confidence_score": 0.20
    }
    persisted = database.add_lead_evidence(persisted_id, invalid_ev)
    assert persisted is False

    # Clean up test lead
    database.remove_lead(persisted_id)

def test_api_evidence_endpoints():
    from dashboard import get_lead_evidence_endpoint, add_lead_evidence_endpoint
    test_id = f"test_api_{int(datetime.now().timestamp())}"
    
    # Pre-populate lead
    lead_dict = {
        "id": test_id,
        "company_name": "Signal Systems",
        "domain": f"signalsys_{int(datetime.now().timestamp())}.io",
        "location": "Austin, US",
        "founder_name": "David Marcus",
        "founder_title": "CEO",
        "email": f"david_{int(datetime.now().timestamp())}@signalsys.io",
        "tech_summary": "Distributed streaming data platform.",
        "deliverability_score": 95,
        "deliverability_status": "IDENTITY_VERIFIED_CURRENT",
        "linkedin_url": "https://www.linkedin.com/in/davidmarcus",
        "icp_reason": "High ICP Fit"
    }
    database.add_lead(lead_dict)
    saved_id = lead_dict["id"]

    # Post verified evidence
    post_res = add_lead_evidence_endpoint(saved_id, {
        "source_url": "https://signalsys.io/blog",
        "evidence_extracted": "Signal Systems announced public beta release of distributed engine.",
        "date_discovered": datetime.now(timezone.utc).isoformat(),
        "confidence_score": 0.90,
        "signal_type": "BUYING_TRIGGER",
        "statement": "Launched public beta release."
    })
    assert post_res.get("success") is True

    # Get evidence
    get_res = get_lead_evidence_endpoint(saved_id)
    assert get_res.get("success") is True
    assert len(get_res["evidence"]) >= 1
    assert get_res["evidence"][0]["source_url"] == "https://signalsys.io/blog"

    # Clean up
    database.remove_lead(saved_id)
