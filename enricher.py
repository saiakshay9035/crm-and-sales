import logging
import time
import requests
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AIEnricher")

PITCH_PROMPT_TEMPLATE = """
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

def retry_request(func, max_retries=3):
    def wrapper(*args, **kwargs):
        retries = 0
        while retries < max_retries:
            try:
                return func(*args, **kwargs)
            except requests.RequestException as e:
                retries += 1
                if retries == max_retries:
                    raise
                sleep_time = 2 ** retries
                logger.warning(f"Request failed: {e}. Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
    return wrapper

class AIProspectEnricher:
    """
    Uses LLMs (Ollama / Groq / Gemini / OpenAI) to research prospects
    and craft hyper-personalized outreach pitches for offshore talent & managed delivery.
    """
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

    @retry_request
    def _call_ollama(self, prompt: str) -> str:
        res = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=10
        )
        res.raise_for_status()
        return res.json().get("response", "").strip()

    @retry_request
    def _call_groq(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": settings.GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            },
            headers=headers,
            timeout=10
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()

    @retry_request
    def _call_openai(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o",  # Defaulting to a generic openai model if not specified, though not in settings
                "messages": [{"role": "user", "content": prompt}]
            },
            headers=headers,
            timeout=10
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()

    def generate_pitch(self, founder_name: str, company_name: str, location: str, summary: str) -> str:
        """Generates a high-converting personalized cold email."""
        
        prompt = PITCH_PROMPT_TEMPLATE.format(
            founder_name=founder_name,
            company_name=company_name,
            location=location,
            summary=summary
        )
        logger.info(f"[AI Enricher] Generating pitch for {founder_name} @ {company_name} using {self.provider}...")

        try:
            if self.provider == "ollama":
                return self._call_ollama(prompt)
            elif self.provider == "groq":
                return self._call_groq(prompt)
            elif self.provider == "openai":
                return self._call_openai(prompt)
            else:
                logger.warning(f"LLM Provider '{self.provider}' not implemented or invalid. Falling back to template.")
        except Exception as e:
            logger.warning(f"[{self.provider}] Error generating pitch ({e}). Falling back to template generator.")

        # Template fallback if LLM server is offline or fails
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
