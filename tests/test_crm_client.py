import pytest
from unittest.mock import patch, MagicMock
from crm_client import CompAICRMClient, CRMError


@pytest.fixture
def crm_client():
    return CompAICRMClient()


def test_create_or_update_company_offline_fallback(crm_client):
    with patch.object(crm_client, '_get_connection', side_effect=Exception("DB Offline")):
        result = crm_client.create_or_update_company("Acme", "acme.com", "NY", "Tech")
        assert result["name"] == "Acme"
        assert result["domain"] == "acme.com"
        assert result["status"] == "LOGGED_LOCAL"


def test_create_or_update_company_success(crm_client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_cursor.fetchone.side_effect = [("author_1",), None, ("comp_123", "Acme", "acme.com")]

    
    with patch.object(crm_client, '_get_connection', return_value=mock_conn):
        result = crm_client.create_or_update_company("Acme", "acme.com", "NY", "Tech")
        assert result["id"] == "comp_123"
        assert result["name"] == "Acme"
        assert result["status"] == "CREATED"


def test_crm_error_exception():
    error = CRMError("test error")
    assert str(error) == "test error"

