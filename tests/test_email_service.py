from unittest.mock import patch

import pytest
import responses

from email_service import EmailService


@pytest.fixture
def email_service():
    return EmailService(
        resend_api_key="test_key",
        from_email="test@example.com",
        business_address="123 Test St"
    )


@responses.activate
def test_send_via_resend_success(email_service):
    responses.add(
        responses.POST,
        "https://api.resend.com/emails",
        json={"id": "resend_123"},
        status=200
    )

    result = email_service.send_via_resend("to@example.com", "Subject", "<p>Body</p>")
    assert result == {"id": "resend_123"}


@responses.activate
def test_send_fallback_to_smtp_on_resend_failure(email_service):
    responses.add(
        responses.POST,
        "https://api.resend.com/emails",
        json={"message": "Unauthorized"},
        status=401
    )

    with patch.object(email_service, 'send_via_smtp', return_value=True) as mock_smtp:
        result = email_service.send("to@example.com", "Subject", "<p>Body</p>", "Body")
        assert result is True
        mock_smtp.assert_called_once()


def test_append_can_spam_footer(email_service):
    html = "<p>Hello</p>"
    result = email_service._append_can_spam_footer(html)
    assert "123 Test St" in result
    assert "unsubscribe" in result.lower()


def test_empty_api_key_behavior():
    service = EmailService(
        resend_api_key="",
        from_email="test@example.com",
        business_address="123 Test St"
    )

    with patch.object(service, 'send_via_smtp') as mock_smtp:
        mock_smtp.return_value = True
        result = service.send("to@example.com", "Subject", "<html></html>", "text")
        assert result is True
        mock_smtp.assert_called_once()
