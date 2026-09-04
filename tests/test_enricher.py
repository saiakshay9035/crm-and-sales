from unittest.mock import patch

import pytest
import responses

from enricher import AIProspectEnricher


@pytest.fixture
def enricher():
    return AIProspectEnricher()

@responses.activate
def test_generate_pitch_ollama_success(enricher, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    
    responses.add(
        responses.POST,
        "http://localhost:11434/api/generate",
        json={"response": "Custom AI Pitch for Jane"},
        status=200
    )
    
    result = enricher.generate_pitch("Jane", "Acme", "NY", "Tech corp")
    assert "Custom AI Pitch for Jane" in result

@responses.activate
def test_fallback_to_template_when_ollama_down(enricher, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    
    responses.add(
        responses.POST,
        "http://localhost:11434/api/generate",
        status=500
    )
    
    result = enricher.generate_pitch("Jane", "Acme", "NY", "Tech corp")
    assert "Jane" in result
    assert "Acme" in result
    assert "I noticed your work" in result or "fallback" in result.lower() or "Jane" in result

def test_fallback_template_content(enricher):
    result = enricher._fallback_template("Jane", "Acme", "NY", "Tech corp")
    assert "Jane" in result
    assert "Acme" in result

@patch("enricher.AIProspectEnricher.generate_pitch")
def test_groq_provider(mock_generate, enricher, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    mock_generate.return_value = "Groq Pitch"
    
    result = enricher.generate_pitch("Jane", "Acme", "NY", "Tech")
    assert result == "Groq Pitch"

@patch("enricher.AIProspectEnricher.generate_pitch")
def test_openai_provider(mock_generate, enricher, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    mock_generate.return_value = "OpenAI Pitch"
    
    result = enricher.generate_pitch("Jane", "Acme", "NY", "Tech")
    assert result == "OpenAI Pitch"
