from unittest.mock import MagicMock, patch

from scraper import StartupLeadScraper, verify_domain_mx


def test_verify_domain_mx_valid():
    assert verify_domain_mx("gmail.com") is True


def test_verify_domain_mx_invalid():
    assert verify_domain_mx("nonexistent-domain-12345-abc.invalid") is False


@patch("scraper.DDGS")
def test_search_real_leads_mocked(mock_ddgs):
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {
            "title": "Kimpton AI: The IDE for Investors | Y Combinator",
            "href": "https://www.ycombinator.com/companies/kimpton-ai",
            "body": "Live Evaluation Arenas for Financial Work. Founded in 2025 by Adrian Del Bosque in New York."
        }
    ]
    mock_ddgs.return_value = mock_instance

    scraper = StartupLeadScraper()
    leads = scraper.search_real_leads("AI startup", limit=1)
    
    assert len(leads) == 1
    assert "company_name" in leads[0]
    assert "domain" in leads[0]
    assert "founder_name" in leads[0]

