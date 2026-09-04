

def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "token")
    monkeypatch.setenv("BUSINESS_ADDRESS", "address")

    from config import Settings
    settings = Settings()
    assert settings.LLM_PROVIDER == "groq"
    assert settings.SMTP_PORT == 587
    assert settings.RESEND_API_KEY == "key"
    assert settings.DASHBOARD_AUTH_TOKEN == "token"
    assert settings.BUSINESS_ADDRESS == "address"


def test_settings_defaults(monkeypatch):
    # Clear keys that might be set by conftest
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DASHBOARD_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("BUSINESS_ADDRESS", raising=False)

    from config import Settings
    settings = Settings()
    assert settings.LLM_PROVIDER == "ollama"
    assert settings.OLLAMA_MODEL == "llama3"
    assert settings.SMTP_PORT == 587
    assert settings.DASHBOARD_AUTH_TOKEN == ""
    assert settings.BUSINESS_ADDRESS == ""


def test_settings_smtp_port_parsing(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    from config import Settings
    settings = Settings()
    assert settings.SMTP_PORT == 465
    assert isinstance(settings.SMTP_PORT, int)
