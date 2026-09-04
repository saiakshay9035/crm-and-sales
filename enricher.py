import logging
import requests
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AIEnricher")

class AIProspectEnricher:
    """
    Uses LLMs (Ollama / Groq / Gemini / OpenAI) to research prospects
    and craft hyper-personalized outreach pitches for offshore talent & managed delivery.
    """
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

    def generate_pitch(self, founder_name: str, company_name: str, location: str, summary: str) -> str:
        """Generates a high-converting personalized cold email."""
        
        prompt = f"""
Write a short, high-converting B2B cold email (under 90 words) offering managed tech talent & project delivery.

Target Lead:
- Founder: {founder_name}
- Company: {company_name} ({location})
- What they do: {summary}

Value Proposition:
- Provide top senior Indian developers (React, Node, Python, Mobile, DevOps).
- Full end-to-end Product & Project Management included (they don't have to manage developers or track sprints).
- Saves 60% compared to local US/EU/AUS developer rates.

Requirements:
- Subject line included.
- Hook mentioning their product/company.
- Direct value offer + low-friction call to action.
- Professional, concise, no fluff or fake praise.
"""
        logger.info(f"[AI Enricher] Generating pitch for {founder_name} @ {company_name} using {self.provider}...")

        # 1. Ollama (100% Free Local Execution)
        if self.provider == "ollama":
            try:
                res = requests.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
                    timeout=10
                )
                if res.status_code == 200:
                    return res.json().get("response", "").strip()
            except Exception as e:
                logger.warning(f"[Ollama] Local Ollama not running ({e}). Falling back to template generator.")

        # 2. Template fallback if LLM server is offline
        return self._fallback_template(founder_name, company_name, location, summary)

    def _fallback_template(self, founder_name: str, company_name: str, location: str, summary: str) -> str:
        return f"""Subject: Scaling {company_name}'s tech team / Quick question

Hi {founder_name},

Saw that {company_name} is scaling its platform in {location}.

Most founders we partner with in {location} struggle with $140k+ local developer salaries and the headache of managing remote freelancers who miss sprint deadlines.

We solve both: We provide senior Indian software engineers AND handle full end-to-end Product & Project Management—so features get delivered on time without taking up your week.

We recently helped a US startup ship their MVP in 60 days at 60% lower cost.

Open to seeing a 2-minute video on how we manage delivery?

Best,
Offshore Delivery Lead"""
