import html
import json
import logging
import time

import requests

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AIEnricher")


PITCH_PROMPT_TEMPLATE = """
Write a short, high-converting B2B cold email (under 90 words).

Target Lead:
- Contact: {founder_name}
- Company: {company_name} ({location})
- What they do: {summary}
- Detected Buying Triggers: {buying_triggers}
- Key Pain Signals: {pain_signals}

Your Value Proposition:
{value_proposition}

Requirements:
- Subject line included (format: "Subject: ..." on first line).
- Hook mentioning their product/company and specific buying triggers/pain signals.
- Direct value offer + low-friction call to action.
- Professional, concise, no fluff or fake praise.
- Sign off with: {sender_name}
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
    Uses LLMs (Ollama / Groq / OpenAI) to research prospects
    and craft hyper-personalized outreach pitches based on user-defined value proposition.
    """
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

    def _call_ollama(self, prompt: str) -> str:
        res = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=15
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
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": prompt}]
            },
            headers=headers,
            timeout=10
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()

    def generate_pitch(
        self,
        founder_name: str,
        company_name: str,
        location: str,
        summary: str,
        buying_triggers: list = None,
        pain_signals: list = None,
        value_proposition: str = "",
        sender_name: str = ""
    ) -> str:
        """Generates a high-converting personalized cold email using detected evidence."""
        
        b_trig = ", ".join(buying_triggers) if isinstance(buying_triggers, list) and buying_triggers else "Growth & scaling"
        p_sig = ", ".join(pain_signals) if isinstance(pain_signals, list) and pain_signals else "Operational efficiency"

        # Use configured identity or fallback
        if not value_proposition:
            value_proposition = getattr(settings, 'VALUE_PROPOSITION', '') or "We help companies like yours solve critical challenges and accelerate growth."
        if not sender_name:
            sender_name = getattr(settings, 'SENDER_NAME', '') or "The Team"

        prompt = PITCH_PROMPT_TEMPLATE.format(
            founder_name=founder_name,
            company_name=company_name,
            location=location,
            summary=summary,
            buying_triggers=b_trig,
            pain_signals=p_sig,
            value_proposition=value_proposition,
            sender_name=sender_name
        )
        logger.info(f"[AI Enricher] Generating evidence-based pitch for {founder_name} @ {company_name} using {self.provider}...")

        pitch = ""
        try:
            if self.provider == "ollama":
                pitch = self._call_ollama(prompt)
            elif self.provider == "groq":
                pitch = self._call_groq(prompt)
            elif self.provider == "openai":
                pitch = self._call_openai(prompt)
            else:
                logger.warning(f"LLM Provider '{self.provider}' not implemented or invalid. Falling back to template.")
        except Exception as e:
            logger.warning(f"[{self.provider}] Error generating pitch ({e}). Falling back to template generator.")

        if not pitch:
            pitch = self._fallback_template(founder_name, company_name, location, summary, buying_triggers, pain_signals)

        return html.unescape(pitch)

    def _fallback_template(
        self,
        founder_name: str,
        company_name: str,
        location: str,
        summary: str,
        buying_triggers: list = None,
        pain_signals: list = None,
        value_proposition: str = "",
        sender_name: str = ""
    ) -> str:
        clean_summary = summary.strip().rstrip(".")
        if " (" in clean_summary:
            clean_summary = clean_summary.split(" (")[0]

        product_hook = f"Saw that {company_name} is building {clean_summary}." if clean_summary else f"Noticed {company_name} is growing in {location}."

        if not sender_name:
            sender_name = getattr(settings, 'SENDER_NAME', '') or "The Team"
        if not value_proposition:
            value_proposition = getattr(settings, 'VALUE_PROPOSITION', '') or ""

        value_line = f"\n{value_proposition}\n" if value_proposition else "\nWe help companies like yours solve key growth challenges with tailored solutions.\n"

        pitch = f"""Subject: Quick question for {company_name}

Hi {founder_name},

{product_hook}
{value_line}
Would love to share how we've helped similar companies. Open to a quick chat this week?

Best,
{sender_name}"""
        return html.unescape(pitch)

