import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # LLM Settings (Supports Ollama for 100% free local execution, or Groq/Gemini free tiers)
    LLM_PROVIDER: str = "ollama"  # "ollama", "groq", "gemini", or "openai"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama3-70b-8192"
    
    OPENAI_API_KEY: str = ""
    
    # Composio API Settings (Managed MCP Gateway: https://connect.composio.dev/mcp)
    COMPOSIO_API_KEY: str = ""

    # Resend API Settings (Live Email Engine)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"

    # TryCompAI CRM (Comp AI CRM) Settings
    CRM_API_URL: str = "http://localhost:3000/api"
    CRM_API_KEY: str = "your_comp_crm_key"
    
    # Email Outreach Settings (SMTP / Free Mailer)
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "your_email@domain.com"
    SMTP_PASS: str = "your_app_password"
    
    # New settings
    DASHBOARD_AUTH_TOKEN: str = ""
    BUSINESS_ADDRESS: str = ""

settings = Settings()
