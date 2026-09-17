"""
Unit tests for Conversational ICP Builder module (icp_builder.py)
"""

import pytest
from icp_builder import icp_builder


def test_parse_prompt_customers_niche():
    prompt = "Find me US SaaS founders who have raised between $500k and $5M, under 20 employees and hiring engineers"
    res = icp_builder.parse_prompt(prompt, target_type="customers")
    
    assert res["target_type"] == "customers"
    assert "United States" in res["geography"]
    assert res["company_size"] == "1-20 employees"
    assert "👨‍💻 Active Hiring & Team Expansion" in res["buying_signals"]
    assert len(res["search_queries"]) > 0


def test_parse_prompt_investors_target():
    prompt = "Find US seed stage venture partners and angels investing $1M-$5M in B2B AI startups"
    res = icp_builder.parse_prompt(prompt, target_type="investors")
    
    assert res["target_type"] == "investors"
    assert "United States" in res["geography"]
    assert "Partner" in res["decision_maker_titles"]
    assert any("venture" in q.lower() or "angel" in q.lower() or "partner" in q.lower() for q in res["search_queries"])


def test_parse_prompt_fallback_geography():
    prompt = "Find tech software founders in Dubai and Sydney"
    res = icp_builder.parse_prompt(prompt, target_type="customers")
    
    assert any(g in res["geography"] for g in ["UAE / Dubai", "Australia"])
    assert res["min_icp_score"] == 80
