import uuid
from typing import Any, Dict, Tuple
from app.features.mcp.client import obsidian_client
from app.logging import get_logger

logger = get_logger()

class McpService:
    async def _execute_request(self, method_name: str, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if obsidian_client is None:
            raise ValueError("MCP_VAULT_URL environment variable not set.")

        trace_id = str(uuid.uuid4())
        logger.info(f"mcp_call_start: trace_id={trace_id}, endpoint={method_name}, payload={payload}")
        
        try:
            method = getattr(obsidian_client, method_name)
            result = method(payload)
            logger.info(f"mcp_call_ok: trace_id={trace_id}, endpoint={method_name}, result_keys={list(result.keys()) if result else 'N/A'}")
            return trace_id, result
        except Exception as e:
            logger.error(f"mcp_call_err: trace_id={trace_id}, endpoint={method_name}, error={e}")
            raise e

    async def search(self, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        return await self._execute_request("search", payload)

    async def fetch(self, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        return await self._execute_request("fetch", payload)

mcp_service = McpService()
