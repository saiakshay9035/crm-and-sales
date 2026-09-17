"""
Comprehensive unit tests for Identity & Employment Cross-Verification Agent (identity_verifier.py)
"""

import pytest
from identity_verifier import identity_agent


def test_verify_identity_valid_match():
    res = identity_agent.verify_lead_identity(
        founder_name="Steven Tey",
        company_name="Dub.co",
        domain="dub.co",
        email="steven@dub.co",
        linkedin_url="https://www.linkedin.com/in/steventey"
    )
    assert res["verified"] is True
    assert res["status"] == "IDENTITY_VERIFIED_CURRENT"


def test_verify_identity_hyphenated_name():
    res = identity_agent.verify_lead_identity(
        founder_name="Jean-Luc Picard",
        company_name="Enterprise AI",
        domain="enterprise.ai",
        email="jeanluc@enterprise.ai",
        linkedin_url="https://www.linkedin.com/in/jeanlucpicard"
    )
    assert res["verified"] is True
    assert res["status"] == "IDENTITY_VERIFIED_CURRENT"


def test_verify_identity_subdomain_corporate():
    res = identity_agent.verify_lead_identity(
        founder_name="Paul Copplestone",
        company_name="Supabase",
        domain="app.supabase.com",
        email="paul@supabase.com",
        linkedin_url="https://www.linkedin.com/in/paulcopplestone"
    )
    assert res["verified"] is True
    assert res["status"] == "IDENTITY_VERIFIED_CURRENT"


def test_verify_identity_rejects_freemail_domain():
    res = identity_agent.verify_lead_identity(
        founder_name="Zeno Rocha",
        company_name="Resend",
        domain="resend.com",
        email="zeno@gmail.com",
        linkedin_url="https://www.linkedin.com/in/zenorocha"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_FREEMAIL_DOMAIN"


def test_verify_identity_rejects_false_positive_name_match():
    res = identity_agent.verify_lead_identity(
        founder_name="John Smith",
        company_name="Acme Corp",
        domain="acme.com",
        email="john@acme.com",
        linkedin_url="https://www.linkedin.com/in/john-doe"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_LINKEDIN_PERSON_MISMATCH"


def test_verify_identity_rejects_domain_mismatch():
    res = identity_agent.verify_lead_identity(
        founder_name="Steven Tey",
        company_name="Dub.co",
        domain="dub.co",
        email="steven@oldcompany.com",
        linkedin_url="https://www.linkedin.com/in/steventey"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_DOMAIN_MISMATCH"


def test_verify_identity_rejects_past_employment_keywords():
    for company, title in [
        ("Dub.co", "Former founder"),
        ("Dub.co", "Former CEO"),
        ("Was founder of Dub", "CEO"),
        ("Dub.co", "Stepped down as CEO"),
        ("Acquired by BigCorp", "Founder"),
    ]:
        res = identity_agent.verify_lead_identity(
            founder_name="Steven Tey",
            company_name=company,
            domain="dub.co",
            email="steven@dub.co",
            linkedin_url="https://www.linkedin.com/in/steventey",
            founder_title=title
        )
        assert res["verified"] is False, f"Should reject: company='{company}', title='{title}'"
        assert res["status"] == "REJECTED_PAST_EMPLOYMENT"


def test_verify_identity_cctld_domain_mismatch():
    res = identity_agent.verify_lead_identity(
        founder_name="Daniel Campion",
        company_name="Sitenna",
        domain="sitenna.com.au",
        email="daniel@othercompany.com.au",
        linkedin_url="https://www.linkedin.com/in/danielcampion"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_DOMAIN_MISMATCH"


def test_verify_identity_rejects_email_person_mismatch():
    res = identity_agent.verify_lead_identity(
        founder_name="Daniel Campion",
        company_name="Sitenna",
        domain="sitenna.com",
        email="alex@sitenna.com",
        linkedin_url="https://www.linkedin.com/in/danielcampion"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_EMAIL_NAME_MISMATCH"


def test_verify_identity_rejects_past_employment_in_title_or_summary():
    # Test that past-employment in founder_title triggers rejection
    res = identity_agent.verify_lead_identity(
        founder_name="Steven Tey",
        company_name="Dub.co",
        domain="dub.co",
        email="steven@dub.co",
        linkedin_url="https://www.linkedin.com/in/steventey",
        founder_title="Former founder",
        tech_summary="Previously built Dub.co, stepped down in 2024"
    )
    assert res["verified"] is False
    assert res["status"] == "REJECTED_PAST_EMPLOYMENT"


def test_verify_identity_allows_ex_employer_in_summary():
    """A current founder who was previously at Google should NOT be rejected."""
    res = identity_agent.verify_lead_identity(
        founder_name="Steven Tey",
        company_name="Dub.co",
        domain="dub.co",
        email="steven@dub.co",
        linkedin_url="https://www.linkedin.com/in/steventey",
        founder_title="Founder & CEO",
        tech_summary="Ex-Google engineer building open source link management"
    )
    assert res["verified"] is True
    assert res["status"] == "IDENTITY_VERIFIED_CURRENT"

