"""
Conversational ICP Builder & Parser
Converts natural language user prompts into structured ICP criteria JSON,
search strategies, and qualification rules for Customers, Investors, Partners, and Hiring.
"""

import json
import logging
import re
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ICPBuilder")


class ConversationalICPBuilder:
    """
    Translates freeform user intent into structured ICP profiles,
    target keywords, intent signal triggers, and scoring thresholds.
    """

    TARGET_TYPES = {
        "customers": "Target Customers & Buyers",
        "investors": "Investors & Funding Partners",
        "partners": "Strategic & Channel Partners",
        "employees": "Talent & Recruitment",
        "recruiters": "Executive Search & Talent Acquisition"
    }

    def parse_prompt(self, prompt: str, target_type: str = "customers") -> Dict[str, Any]:
        """Parses natural language prompt into structured ICP specification using rule-based extraction."""
        target_type_clean = target_type.lower().strip()
        if target_type_clean not in self.TARGET_TYPES:
            target_type_clean = "customers"

        prompt_lower = prompt.lower()

        # Extract Geography
        geography = []
        if any(k in prompt_lower for k in ["us", "usa", "united states", "san francisco", "ny", "new york", "austin"]):
            geography.append("United States")
        if any(k in prompt_lower for k in ["uk", "london", "united kingdom", "britain"]):
            geography.append("United Kingdom")
        if any(k in prompt_lower for k in ["eu", "europe", "germany", "sweden", "france"]):
            geography.append("Europe")
        if any(k in prompt_lower for k in ["dubai", "uae", "middle east"]):
            geography.append("UAE / Dubai")
        if any(k in prompt_lower for k in ["sydney", "australia", "aus"]):
            geography.append("Australia")

        if not geography:
            geography = ["Global"]

        # Extract Company Size / Stage
        company_size = "Any size"
        if any(k in prompt_lower for k in ["1-10", "under 10", "fewer than 10", "small team"]):
            company_size = "1-10 employees"
        elif any(k in prompt_lower for k in ["under 20", "1-20", "fewer than 20"]):
            company_size = "1-20 employees"
        elif any(k in prompt_lower for k in ["10-50", "under 50", "fewer than 50", "mid-size", "midsize"]):
            company_size = "10-50 employees"
        elif any(k in prompt_lower for k in ["50-200", "under 200", "medium"]):
            company_size = "50-200 employees"
        elif any(k in prompt_lower for k in ["200+", "enterprise", "large"]):
            company_size = "200+ employees"

        # Extract Stage / Funding
        stage = []
        if any(k in prompt_lower for k in ["pre-seed", "pre seed", "preseed"]):
            stage.append("Pre-Seed")
        if "seed" in prompt_lower and "pre" not in prompt_lower:
            stage.append("Seed")
        if "series a" in prompt_lower:
            stage.append("Series A")
        if "series b" in prompt_lower:
            stage.append("Series B")
        if not stage:
            stage = ["Any"]

        funding = "Any"
        if "$500k" in prompt_lower or "$1m" in prompt_lower or "$5m" in prompt_lower:
            funding = "$500K - $5M"
        elif any(k in prompt_lower for k in ["pre-seed", "seed", "angel"]):
            funding = "Pre-seed / Seed"
        elif any(k in prompt_lower for k in ["series a", "series b", "venture"]):
            funding = "Venture / Growth"

        # Decision Maker Titles
        titles = ["Founder", "Co-Founder", "CEO", "Owner"]
        if target_type_clean == "investors":
            titles = ["Partner", "General Partner", "Managing Director", "Principal"]
        elif target_type_clean == "employees":
            titles = ["Software Engineer", "Developer", "Designer", "Product Manager"]
        elif "cto" in prompt_lower or "engineer" in prompt_lower:
            titles = ["CTO", "VP Engineering", "Head of Product"]
        elif any(k in prompt_lower for k in ["doctor", "dentist", "clinic", "medical", "healthcare"]):
            titles = ["Owner", "Practice Manager", "Medical Director", "CEO"]
        elif any(k in prompt_lower for k in ["lawyer", "attorney", "law firm", "legal"]):
            titles = ["Managing Partner", "Senior Partner", "Owner"]
        elif any(k in prompt_lower for k in ["restaurant", "cafe", "food", "hospitality"]):
            titles = ["Owner", "General Manager", "Founder"]
        elif any(k in prompt_lower for k in ["real estate", "property", "realty"]):
            titles = ["Broker", "Owner", "Managing Director", "CEO"]
        elif any(k in prompt_lower for k in ["agency", "consulting", "consultant"]):
            titles = ["Founder", "Managing Director", "CEO", "Principal"]

        # Intent Signals
        buying_signals = ["Active Product Development"]
        if any(k in prompt_lower for k in ["hiring", "engineer", "developer", "roles"]):
            buying_signals.append("👨‍💻 Active Hiring & Team Expansion")
        if any(k in prompt_lower for k in ["funded", "raised", "seed", "vc", "yc"]):
            buying_signals.append("💰 Recent Capital Raise / VC Backed")
        if any(k in prompt_lower for k in ["launch", "v2", "open source"]):
            buying_signals.append("🚀 Core Feature Scaling / New Launch")

        # Compile Search Queries
        search_queries = self._generate_search_queries(target_type_clean, geography, titles, prompt)

        return {
            "target_type": target_type_clean,
            "target_type_label": self.TARGET_TYPES[target_type_clean],
            "raw_prompt": prompt,
            "geography": geography,
            "company_size": company_size,
            "stage": stage,
            "funding": funding,
            "decision_maker_titles": titles,
            "buying_signals": buying_signals,
            "min_icp_score": 80,
            "search_queries": search_queries
        }

    def _generate_search_queries(self, target_type: str, geography: List[str], titles: List[str], prompt: str) -> List[str]:
        """Generates diverse search queries tailored to the user's specific niche and geography."""
        prompt_clean = prompt.strip()
        prompt_lower = prompt.lower()
        geo_str = " ".join(geography) if geography and geography != ["Global"] else ""

        # Remove common stop words to extract core niche/industry keywords
        filler_words = {
            "find", "me", "leads", "for", "in", "with", "that", "want", "need", "to", "reach",
            "search", "looking", "who", "are", "under", "fewer", "than",
            "employees", "staff", "team", "size", "located", "based", "company", "companies",
            "get", "show", "give", "all", "our", "their", "the", "and", "can", "has", "have",
            "been", "will", "would", "could", "should", "any", "some"
        }
        # Don't filter out industry-specific words that happen to match geo names
        geo_words = {"united", "states"} if "united states" in prompt_lower else set()
        words = re.findall(r'\b[a-zA-Z]{3,}\b', prompt_lower)
        niche_words = [w for w in words if w not in filler_words and w not in geo_words]

        # Use more niche words (up to 5) for better search specificity
        niche_topic = " ".join(niche_words[:5]) if niche_words else prompt_clean
        title_str = " OR ".join(titles[:2]) if titles else "founder OR CEO OR owner"

        queries = [
            f"{prompt_clean} contact email",
            f"{niche_topic} {title_str} {geo_str} email OR contact",
            f"{niche_topic} company {geo_str} founder OR owner OR CEO",
            f"{niche_topic} {geo_str} business owner director contact"
        ]

        clean_queries = [re.sub(r'\s+', ' ', q).strip() for q in queries]
        return clean_queries


# Singleton instance
icp_builder = ConversationalICPBuilder()
