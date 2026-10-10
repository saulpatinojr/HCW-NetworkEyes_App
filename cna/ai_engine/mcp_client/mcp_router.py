"""MCP Router — Phase D (DD-003).

Routes recommendation requests to the appropriate MCP server:
  - AWS findings -> awslabs/mcp (AWS MCP Server)
  - Azure findings -> Microsoft Azure MCP Server

Fallback chain:
  1. Try cloud-specific MCP server
  2. On timeout or error: return empty list (RecommendationEngine applies offline fallback)

Contract:
  - This module ONLY fetches recommendations.
  - It never reads topology data or generates findings.
  - It never writes to EngagementStore.
"""

from __future__ import annotations

import logging

from cna.ai_engine.mcp_client.aws_mcp_client import AWSMCPClient
from cna.ai_engine.mcp_client.azure_mcp_client import AzureMCPClient
from cna.core.findings_schema import FindingRecommendation

logger = logging.getLogger("cna.mcp.router")


class MCPRouter:
    """Routes recommendation requests to the correct MCP client."""

    def __init__(
        self,
        aws_client: AWSMCPClient | None = None,
        azure_client: AzureMCPClient | None = None,
    ):
        self._aws = aws_client or AWSMCPClient()
        self._azure = azure_client or AzureMCPClient()

    def get_recommendations(
        self,
        cloud: str,
        rule_id: str,
        resource_type: str,
        finding_title: str,
    ) -> list[FindingRecommendation]:
        """Fetch recommendations from the appropriate MCP server.

        Args:
            cloud: "aws" or "azure" (case-insensitive)
            rule_id: e.g. "AWS-NET-003"
            resource_type: e.g. "AWS::EC2::SecurityGroup"
            finding_title: human-readable title for context

        Returns:
            List of FindingRecommendation. Empty list if MCP unavailable.
        """
        cloud_lower = cloud.lower()
        try:
            if cloud_lower == "aws" or resource_type.startswith("AWS"):
                return self._aws.get_recommendations(
                    rule_id=rule_id,
                    resource_type=resource_type,
                    finding_title=finding_title,
                )
            elif cloud_lower == "azure" or resource_type.startswith("Microsoft"):
                return self._azure.get_recommendations(
                    rule_id=rule_id,
                    resource_type=resource_type,
                    finding_title=finding_title,
                )
            else:
                logger.warning(
                    "Unknown cloud '%s' for rule %s — no MCP client available", cloud, rule_id
                )
                return []
        except Exception as e:
            logger.warning("MCPRouter: error fetching recommendations for %s: %s", rule_id, e)
            return []
