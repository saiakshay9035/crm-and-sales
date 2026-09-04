import pytest
import responses
from unittest.mock import patch
from crm_client import CompAICRMClient, CRMError


@pytest.fixture
def crm_client():
    return CompAICRMClient()


@responses.activate
def test_create_or_update_company_success(crm_client):
    responses.add(
        responses.POST,
        "http://localhost:3000/api/companies",
        json={"id": "comp_123", "name": "Acme"},
        status=200,
    )

    result = crm_client.create_or_update_company("Acme", "acme.com", "NY", "Tech")
    assert result == {"id": "comp_123", "name": "Acme"}


@responses.activate
def test_create_or_update_company_offline_fallback(crm_client):
    responses.add(
        responses.POST,
        "http://localhost:3000/api/companies",
        status=500,
    )

    result = crm_client.create_or_update_company("Acme", "acme.com", "NY", "Tech")
    # Expected offline fallback returns local dict
    assert "id" in result
    assert result["name"] == "Acme"
    assert result["status"] == "LOGGED_LOCAL"


@responses.activate
def test_log_interaction_doesnt_crash_on_failure(crm_client):
    responses.add(
        responses.POST,
        "http://localhost:3000/api/interactions",
        status=500,
    )

    # Should not raise exception
    try:
        crm_client.log_interaction("cont_123", "email_sent", "Content")
    except Exception as e:
        pytest.fail(f"log_interaction raised an exception: {e}")


def test_crm_error_exception():
    """Test that CRMError can be instantiated."""
    error = CRMError("test error")
    assert str(error) == "test error"
