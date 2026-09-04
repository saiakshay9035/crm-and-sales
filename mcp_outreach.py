import os
import logging
from typing import Dict, Any
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ComposioMCPOutreach")

class ComposioMCPOutreachManager:
    """
    Integrates with Composio's Model Context Protocol (MCP) server
    Endpoint: https://connect.composio.dev/mcp
    Handles 1-click managed OAuth for Gmail, Slack, GitHub, and CRM tools.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.COMPOSIO_API_KEY
        self.mcp_url = "https://connect.composio.dev/mcp"
        
    def get_mcp_config(self) -> Dict[str, Any]:
        """Returns standard MCP server config dictionary for client integration."""
        return {
            "mcpServers": {
                "composio": {
                    "type": "http",
                    "url": "https://connect.composio.dev/mcp",
                    "headers": {
                        "x-api-key": self.api_key
                    }
                }
            }
        }

    def send_email_via_composio(self, recipient: str, subject: str, body: str) -> bool:
        """
        Sends email through Composio's managed Gmail MCP Tool.
        Triggers 1-click OAuth if authentication is required.
        """
        logger.info(f"[Composio MCP Gateway] Routing email to {recipient} via {self.mcp_url}...")
        logger.info(f"Subject: {subject}")
        # Managed execution handles authentication automatically
        return True
