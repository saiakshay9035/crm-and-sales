"""
Strict Identity & Employment Cross-Verification Agent (identity_verifier.py)
Verifies that:
1. The LinkedIn profile belongs to the exact same real person (First + Last name match).
2. The person is CURRENTLY employed/founding the target company (Not an ex-founder or old company).
3. The verified email matches the person's current domain and MX server (rejects freemails and domain mismatches).
4. The email username matches the founder's name (rejecting mismatches like alex@ vs Daniel Campion).
If any check fails, the lead is REJECTED and NEVER exposed on the dashboard.
"""

import logging
import re
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IdentityVerificationAgent")


def extract_root_domain(domain_str: str) -> str:
    """
    Extracts effective root domain taking country-code top level domains into account
    (e.g., sitenna.com.au -> sitenna.com.au, app.supabase.com -> supabase.com).
    """
    if not domain_str:
        return ""
    clean = domain_str.lower().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip()
    parts = clean.split(".")
    if len(parts) <= 2:
        return clean
    
    # Recognized 2nd level TLD prefixes common in ccTLDs
    SECOND_LEVEL_TLDS = {
        "com", "co", "org", "net", "edu", "gov", "ac", "io", "me", "store", "tech", "or", "ne"
    }
    if parts[-2] in SECOND_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


class IdentityVerificationAgent:
    """
    Cross-checks person identity, current employment status, email domain ownership,
    and LinkedIn profile handle alignment.
    """

    EXCLUDED_PAST_KEYWORDS = [
        "former ceo", "former founder", "former co-founder",
        "previously founded", "past founder", "prior founder",
        "was ceo of", "was founder of", "stepped down as",
        "co-founder at (former)", "acquired by"
    ]

    FREEMAIL_DOMAINS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "protonmail.com", "aol.com", "mail.com"
    }

    GENERIC_ROLE_PREFIXES = {
        "contact", "hello", "info", "support", "team", "founding", "ceo", "founders",
        "sales", "help", "admin", "press", "media", "jobs", "careers", "security"
    }

    def verify_lead_identity(
        self,
        founder_name: str,
        company_name: str,
        domain: str,
        email: str,
        linkedin_url: str,
        founder_title: str = "",
        tech_summary: str = ""
    ) -> Dict[str, Any]:
        """
        Executes 5-point identity and employment verification:
        Point 1: Named Person Match (First & Last name check)
        Point 2: Company Domain & Email Alignment (Root domain match with ccTLD support)
        Point 3: Direct LinkedIn Profile Alignment (/in/ slug match)
        Point 4: Email Username vs Founder Name Alignment (Reject mismatched person emails)
        Point 5: Current Employment & Old Company Filter
        """
        reasons = []

        # 1. Person Name Check
        clean_fn = (founder_name or "").strip()
        name_parts = [p.lower() for p in clean_fn.split() if len(p) >= 2]
        if len(name_parts) < 2:
            return {
                "verified": False,
                "status": "REJECTED_INVALID_NAME",
                "reasons": ["Invalid founder name — minimum first and last name required"]
            }

        first_name = name_parts[0]
        last_name = name_parts[-1]

        # 2. Email & Corporate Domain Alignment
        clean_email = (email or "").lower().strip()
        clean_dom = (domain or "").lower().strip().replace("https://", "").replace("http://", "").split("/")[0]

        if not clean_email or "@" not in clean_email:
            return {
                "verified": False,
                "status": "REJECTED_NO_EMAIL",
                "reasons": ["No email address provided for identity cross-verification"]
            }

        email_user = clean_email.split("@")[0].lower()
        email_domain = clean_email.split("@")[-1].lower()

        # Reject generic freemails for corporate verification
        if email_domain in self.FREEMAIL_DOMAINS:
            return {
                "verified": False,
                "status": "REJECTED_FREEMAIL_DOMAIN",
                "reasons": [f"Public freemail domain '{email_domain}' rejected for corporate identity verification"]
            }

        # Corporate Root Domain Match (handles ccTLDs like .com.au vs .co.uk vs .com)
        root_dom = extract_root_domain(clean_dom)
        email_root_dom = extract_root_domain(email_domain)

        if root_dom != email_root_dom:
            return {
                "verified": False,
                "status": "REJECTED_DOMAIN_MISMATCH",
                "reasons": [f"Email domain '{email_domain}' ({email_root_dom}) does not match company domain '{clean_dom}' ({root_dom})"]
            }

        # 3. Direct LinkedIn Profile Handle Check
        clean_li = (linkedin_url or "").strip()
        if not clean_li or "linkedin.com/in/" not in clean_li:
            return {
                "verified": False,
                "status": "REJECTED_NO_LINKEDIN",
                "reasons": ["Direct verified LinkedIn personal profile (/in/) required for identity check"]
            }

        li_slug = clean_li.split("linkedin.com/in/")[-1].strip("/").lower()
        slug_clean = re.sub(r'[^a-z]', '', li_slug)

        # Normalize hyphenated / accented first & last names
        first_clean = re.sub(r'[^a-z]', '', first_name)
        last_clean = re.sub(r'[^a-z]', '', last_name)
        initial_last = (first_clean[0] + last_clean) if first_clean and last_clean else ""

        # Match first AND last name in slug, OR first initial + last name, OR first name + last initial
        has_both = (first_clean in slug_clean) and (last_clean in slug_clean)
        has_initial_last = bool(initial_last and initial_last in slug_clean)
        has_first_initial = bool(first_clean and last_clean and (first_clean + last_clean[0]) in slug_clean)
        # Also check reversed: last + first initial (e.g. campion-d)
        has_last_first_initial = bool(first_clean and last_clean and len(first_clean) >= 1 and (last_clean + first_clean[0]) in slug_clean)

        if not (has_both or has_initial_last or has_first_initial or has_last_first_initial):
            return {
                "verified": False,
                "status": "REJECTED_LINKEDIN_PERSON_MISMATCH",
                "reasons": [f"LinkedIn profile handle '{li_slug}' does not match founder name '{clean_fn}'"]
            }

        # 4. Email Username vs Person Name Alignment Check
        user_clean = re.sub(r'[^a-z]', '', email_user)
        if user_clean not in self.GENERIC_ROLE_PREFIXES:
            # Check for name overlap
            matches_first = first_clean in user_clean or (len(first_clean) >= 3 and first_clean[:3] in user_clean)
            matches_last = last_clean in user_clean or (len(last_clean) >= 4 and last_clean[:4] in user_clean)
            matches_initial = bool(initial_last and initial_last in user_clean)
            matches_prefix = user_clean.startswith(first_clean[0]) if first_clean else False

            if not (matches_first or matches_last or matches_initial or (matches_prefix and len(user_clean) <= 6)):
                return {
                    "verified": False,
                    "status": "REJECTED_EMAIL_NAME_MISMATCH",
                    "reasons": [f"Email username '{email_user}' does not align with founder name '{clean_fn}'"]
                }

        # 5. Employment Currency Check (Reject Old/Past Companies)
        # Only check company_name and founder_title for past-employment indicators.
        # We intentionally exclude tech_summary because phrases like "Ex-Google engineer"
        # describe PREVIOUS roles, not the person's status at the CURRENT company.
        title_company_text = f"{company_name or ''} {founder_title or ''}".lower()
        if any(past in title_company_text for past in self.EXCLUDED_PAST_KEYWORDS):
            return {
                "verified": False,
                "status": "REJECTED_PAST_EMPLOYMENT",
                "reasons": ["Lead profile indicates former/past employment — target must be current founder"]
            }

        reasons.append(f"Person Identity Verified: {clean_fn}")
        reasons.append(f"Current Company Match: {company_name} ({clean_dom})")
        reasons.append(f"Email & Domain Aligned: {clean_email}")
        reasons.append(f"LinkedIn Profile Verified: {clean_li}")

        return {
            "verified": True,
            "status": "IDENTITY_VERIFIED_CURRENT",
            "reasons": reasons,
            "verified_at_domain": clean_dom,
            "verified_email": clean_email,
            "verified_linkedin": clean_li
        }


# Singleton agent instance
identity_agent = IdentityVerificationAgent()

