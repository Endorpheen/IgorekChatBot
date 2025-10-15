import os
import requests
from typing import Any, Dict
from app.logging import get_logger

logger = get_logger()

class ObsidianClient:
    def __init__(self):
        self.base_url = os.getenv("MCP_VAULT_URL")
        if not self.base_url:
            logger.error("MCP_VAULT_URL environment variable not set.")
            raise ValueError("MCP_VAULT_URL environment variable not set. Please configure it in your .env file.")

    def _request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out.")
            raise RuntimeError("Request timed out")
        except requests.exceptions.ConnectionError:
            logger.error(f"Could not connect to {url}. Is the service running and on the same network?")
            raise RuntimeError("Connection refused")
        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred during the request to {url}: {e}")
            raise e

    def search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("search", payload)

    def fetch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("fetch", payload)

try:
    obsidian_client = ObsidianClient()
except ValueError:
    obsidian_client = None
