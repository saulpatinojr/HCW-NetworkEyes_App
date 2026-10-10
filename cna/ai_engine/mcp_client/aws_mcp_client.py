"""AWS MCP Client — Phase D.

Connects to awslabs/mcp (AWS MCP Server) to fetch Well-Architected and
service-specific recommendations for network findings.

MCP server: https://github.com/awslabs/mcp
Recommended tool: aws.well-architected.get-recommendation

Connection:
  - Requires a remote MCP server accessible via streamable HTTP
  - Configured via env vars: CNA_AWS_MCP_ENDPOINT, CNA_AWS_MCP_TRANSPORT
  - Default transport: streamable-http (public AWS MCP endpoint)
  - Graceful degradation: on ImportError or connection failure, returns []
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from cna.core.findings_schema import FindingRecommendation

logger = logging.getLogger("cna.mcp.aws")

_MCP_ENDPOINT = os.getenv("CNA_AWS_MCP_ENDPOINT", "")
_MCP_TRANSPORT = os.getenv("CNA_AWS_MCP_TRANSPORT", "streamable-http")


class AWSMCPClient:
    """Client for awslabs/mcp AWS MCP Server.

    Falls back gracefully if MCP SDK is not installed or server is unreachable.
    """

    def __init__(
        self,
        endpoint: str = _MCP_ENDPOINT,
        transport: str = _MCP_TRANSPORT,
    ):
        self._endpoint = endpoint
        self._transport = transport
        self._session = None
        self._available = False
        self._try_init()

    def _try_init(self) -> None:
        """Mark the client available when a usable transport is configured.

        Streamable HTTP endpoints do not require the optional MCP SDK. Other
        transports keep the old SDK-gated behavior.
        """
        if self._endpoint and self._transport.lower() in {"streamable-http", "http", "sse"}:
            self._available = True
            logger.info(
                "AWS MCP client initialized (endpoint=%s, transport=%s)",
                self._endpoint,
                self._transport,
            )
            return

        try:
            import mcp  # noqa: F401 — optional dependency

            self._available = True
            logger.info(
                "AWS MCP client initialized (transport=%s)",
                self._transport,
            )
        except ImportError:
            logger.info(
                "mcp package not installed. AWS MCP client operating in "
                "offline mode. Install with: pip install mcp"
            )
            self._available = False

    def get_recommendations(
        self,
        rule_id: str,
        resource_type: str,
        finding_title: str,
    ) -> list[FindingRecommendation]:
        """Fetch recommendations from AWS MCP Server.

        Returns empty list if MCP is unavailable; the caller applies the
        offline fallback.
        """
        if not self._available:
            return []

        try:
            # MCP tool call: aws.well-architected.get-recommendation
            # When the mcp SDK is present, this sends the tool call to the
            # MCP server.
            # The tool takes: pillar, resource_type, issue_description
            # Returns: list of recommendation objects with text + reference_url
            result = self._call_mcp_tool(
                tool_name="aws.well-architected.get-recommendation",
                params={
                    "resource_type": resource_type,
                    "issue_description": finding_title,
                },
            )
            return [
                FindingRecommendation(
                    source="AWS MCP Server (awslabs/mcp)",
                    text=r.get("recommendation", ""),
                    reference_url=r.get("reference_url", ""),
                )
                for r in (result or [])
                if r.get("recommendation")
            ]
        except Exception as e:
            logger.warning("AWS MCP tool call failed for %s: %s", rule_id, e)
            return []

    def _call_mcp_tool(self, tool_name: str, params: dict) -> list[dict]:
        """Execute an MCP tool call. Returns parsed result list.

        Streamable HTTP endpoints use the MCP JSON-RPC `tools/call` method.
        Non-HTTP transports still return [] so callers use offline fallback.
        Raises on transport error — caller handles gracefully.
        """
        if self._endpoint and self._transport.lower() in {"streamable-http", "http", "sse"}:
            response = httpx.post(
                self._endpoint,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": params,
                    },
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
            return _extract_recommendations(response.json())

        logger.debug(
            "MCP tool call skipped for non-HTTP transport: %s",
            tool_name,
        )
        return []


def _extract_recommendations(payload: dict[str, Any]) -> list[dict]:
    """Normalize common MCP tool response shapes into recommendation dicts."""
    result = payload.get("result", payload)
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if not isinstance(result, dict):
        return []

    for key in ("recommendations", "items", "data"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("recommendations", "items", "data"):
            value = structured.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if structured.get("recommendation"):
            return [structured]

    content = result.get("content")
    if isinstance(content, list):
        parsed: list[dict] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("recommendation"):
                parsed.append(item)
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parsed.append(
                    {
                        "recommendation": text.strip(),
                        "reference_url": item.get("uri") or item.get("url") or "",
                    }
                )
        return parsed

    if result.get("recommendation"):
        return [result]
    return []
