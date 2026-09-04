import os
from dataclasses import dataclass

@dataclass
class Settings:
    # LLM Settings (Supports Ollama for 100% free local execution, or Groq/Gemini free tiers)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")  # "ollama", "groq", "gemini", or "openai"
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-70b-8192")
    
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Composio API Settings (Managed MCP Gateway: https://connect.composio.dev/mcp)
    COMPOSIO_API_KEY: str = os.getenv("COMPOSIO_API_KEY", "ck_voTAQE7vjzMCGR-GxLNk")

    # TryCompAI CRM (Comp AI CRM) Settings
    CRM_API_URL: str = os.getenv("CRM_API_URL", "http://localhost:3000/api")
    CRM_API_KEY: str = os.getenv("CRM_API_KEY", "your_comp_crm_key")
    
    # Email Outreach Settings (SMTP / Free Mailer)
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "your_email@domain.com")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "your_app_password")

settings = Settings()
