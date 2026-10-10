"""Unit tests for MCP clients and MCPRouter — offline/fallback paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from cna.ai_engine.mcp_client.aws_mcp_client import AWSMCPClient
from cna.ai_engine.mcp_client.azure_mcp_client import AzureMCPClient
from cna.ai_engine.mcp_client.mcp_router import MCPRouter
from cna.core.findings_schema import FindingRecommendation

# ── AWSMCPClient ───────────────────────────────────────────────────────────────


class TestAWSMCPClient:
    def test_init_marks_unavailable_when_mcp_not_installed(self):
        """mcp package absent → _available=False, no crash."""
        with patch.dict("sys.modules", {"mcp": None}):
            client = AWSMCPClient()
        assert client._available is False

    def test_get_recommendations_returns_empty_when_unavailable(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._available = False
        result = client.get_recommendations(
            rule_id="AWS-NET-001",
            resource_type="AWS::EC2::VPC",
            finding_title="Default VPC in use",
        )
        assert result == []

    def test_get_recommendations_returns_list_when_tool_call_returns_data(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._available = True
        client._transport = "stdio"
        client._endpoint = ""
        with patch.object(
            client,
            "_call_mcp_tool",
            return_value=[
                {
                    "recommendation": "Delete default VPCs",
                    "reference_url": "https://docs.aws.amazon.com/vpc",
                }
            ],
        ):
            result = client.get_recommendations(
                rule_id="AWS-NET-001",
                resource_type="AWS::EC2::VPC",
                finding_title="Default VPC",
            )
        assert len(result) == 1
        assert isinstance(result[0], FindingRecommendation)
        assert result[0].text == "Delete default VPCs"
        assert result[0].source == "AWS MCP Server (awslabs/mcp)"

    def test_get_recommendations_skips_empty_recommendations(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._available = True
        client._transport = "stdio"
        client._endpoint = ""
        with patch.object(
            client,
            "_call_mcp_tool",
            return_value=[
                {"recommendation": "", "reference_url": ""},
                {"recommendation": "Valid rec", "reference_url": "https://example.com"},
            ],
        ):
            result = client.get_recommendations(
                rule_id="AWS-NET-001",
                resource_type="AWS::EC2::VPC",
                finding_title="Test",
            )
        # Empty recommendation must be filtered out
        assert len(result) == 1
        assert result[0].text == "Valid rec"

    def test_get_recommendations_returns_empty_on_exception(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._available = True
        client._transport = "stdio"
        client._endpoint = ""
        with patch.object(client, "_call_mcp_tool", side_effect=ConnectionError("timeout")):
            result = client.get_recommendations(
                rule_id="AWS-NET-001",
                resource_type="AWS::EC2::VPC",
                finding_title="Test",
            )
        assert result == []

    def test_call_mcp_tool_returns_empty_for_non_http_transport(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._endpoint = ""
        client._transport = "stdio"
        result = client._call_mcp_tool("aws.well-architected.get-recommendation", {})
        assert result == []

    def test_call_mcp_tool_posts_json_rpc_to_streamable_http_endpoint(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._endpoint = "https://aws-mcp.example.test/mcp"
        client._transport = "streamable-http"
        response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://aws-mcp.example.test/mcp"),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Associate the Web ACL with the public ALB.",
                        }
                    ]
                },
            },
        )

        with patch(
            "cna.ai_engine.mcp_client.aws_mcp_client.httpx.post", return_value=response
        ) as post:
            result = client._call_mcp_tool(
                "aws.well-architected.get-recommendation",
                {"resource_type": "AWS::WAFv2::WebACL"},
            )

        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        assert payload["method"] == "tools/call"
        assert payload["params"]["name"] == "aws.well-architected.get-recommendation"
        assert result == [
            {
                "recommendation": "Associate the Web ACL with the public ALB.",
                "reference_url": "",
            }
        ]

    def test_constructor_stores_endpoint_and_transport(self):
        client = AWSMCPClient.__new__(AWSMCPClient)
        client._available = False
        client._endpoint = "http://localhost:8080"
        client._transport = "sse"
        assert client._endpoint == "http://localhost:8080"
        assert client._transport == "sse"


# ── AzureMCPClient ─────────────────────────────────────────────────────────────


class TestAzureMCPClient:
    def test_init_marks_unavailable_when_mcp_not_installed(self):
        with patch.dict("sys.modules", {"mcp": None}):
            client = AzureMCPClient()
        assert client._available is False

    def test_get_recommendations_returns_empty_when_unavailable(self):
        client = AzureMCPClient.__new__(AzureMCPClient)
        client._available = False
        result = client.get_recommendations(
            rule_id="AZ-NET-001",
            resource_type="Microsoft.Network/virtualNetworks",
            finding_title="No DDoS protection",
        )
        assert result == []

    def test_get_recommendations_returns_list_when_tool_call_returns_data(self):
        client = AzureMCPClient.__new__(AzureMCPClient)
        client._available = True
        client._transport = "sse"
        client._endpoint = ""
        with patch.object(
            client,
            "_call_mcp_tool",
            return_value=[
                {
                    "recommendation": "Enable DDoS Protection",
                    "reference_url": "https://learn.microsoft.com/azure/ddos",
                }
            ],
        ):
            result = client.get_recommendations(
                rule_id="AZ-NET-001",
                resource_type="Microsoft.Network/virtualNetworks",
                finding_title="No DDoS",
            )
        assert len(result) == 1
        assert result[0].source == "Azure MCP Server (Azure/azure-mcp)"

    def test_get_recommendations_returns_empty_on_exception(self):
        client = AzureMCPClient.__new__(AzureMCPClient)
        client._available = True
        client._transport = "sse"
        client._endpoint = ""
        with patch.object(client, "_call_mcp_tool", side_effect=TimeoutError("timeout")):
            result = client.get_recommendations(
                rule_id="AZ-NET-001",
                resource_type="Microsoft.Network/virtualNetworks",
                finding_title="Test",
            )
        assert result == []

    def test_call_mcp_tool_returns_empty_for_non_http_transport(self):
        client = AzureMCPClient.__new__(AzureMCPClient)
        client._endpoint = ""
        client._transport = "stdio"
        result = client._call_mcp_tool("azure.advisor.get-recommendation", {})
        assert result == []

    def test_call_mcp_tool_posts_json_rpc_to_streamable_http_endpoint(self):
        client = AzureMCPClient.__new__(AzureMCPClient)
        client._endpoint = "https://azure-mcp.example.test"
        client._transport = "streamable-http"
        response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://azure-mcp.example.test"),
            json={
                "result": {
                    "structuredContent": {
                        "recommendations": [
                            {
                                "recommendation": "Move the WAF policy to Prevention mode.",
                                "reference_url": "https://learn.microsoft.com/azure/web-application-firewall/",
                            }
                        ]
                    }
                }
            },
        )

        with patch(
            "cna.ai_engine.mcp_client.azure_mcp_client.httpx.post", return_value=response
        ) as post:
            result = client._call_mcp_tool(
                "azure.advisor.get-recommendation",
                {"resource_type": "Microsoft.Network/frontDoorWebApplicationFirewallPolicies"},
            )

        post.assert_called_once()
        assert post.call_args.kwargs["json"]["method"] == "tools/call"
        assert result[0]["recommendation"] == "Move the WAF policy to Prevention mode."


# ── MCPRouter ──────────────────────────────────────────────────────────────────


class TestMCPRouter:
    def _make_router(self):
        aws_mock = MagicMock()
        azure_mock = MagicMock()
        aws_mock.get_recommendations.return_value = [
            FindingRecommendation(
                source="aws-mcp",
                text="AWS recommendation",
                reference_url="https://aws.example.com",
            )
        ]
        azure_mock.get_recommendations.return_value = [
            FindingRecommendation(
                source="azure-mcp",
                text="Azure recommendation",
                reference_url="https://azure.example.com",
            )
        ]
        return MCPRouter(aws_client=aws_mock, azure_client=azure_mock), aws_mock, azure_mock

    def test_routes_aws_by_cloud_param(self):
        router, aws_mock, azure_mock = self._make_router()
        result = router.get_recommendations(
            cloud="aws",
            rule_id="AWS-NET-001",
            resource_type="AWS::EC2::VPC",
            finding_title="Default VPC",
        )
        aws_mock.get_recommendations.assert_called_once()
        azure_mock.get_recommendations.assert_not_called()
        assert result[0].source == "aws-mcp"

    def test_routes_azure_by_cloud_param(self):
        router, aws_mock, azure_mock = self._make_router()
        result = router.get_recommendations(
            cloud="azure",
            rule_id="AZ-NET-001",
            resource_type="Microsoft.Network/virtualNetworks",
            finding_title="DDoS",
        )
        azure_mock.get_recommendations.assert_called_once()
        aws_mock.get_recommendations.assert_not_called()
        assert result[0].source == "azure-mcp"

    def test_routes_by_resource_type_prefix_aws(self):
        router, aws_mock, azure_mock = self._make_router()
        router.get_recommendations(
            cloud="unknown",
            rule_id="AWS-NET-001",
            resource_type="AWS::EC2::SecurityGroup",
            finding_title="test",
        )
        aws_mock.get_recommendations.assert_called_once()

    def test_routes_by_resource_type_prefix_azure(self):
        router, aws_mock, azure_mock = self._make_router()
        router.get_recommendations(
            cloud="unknown",
            rule_id="AZ-NET-001",
            resource_type="Microsoft.Network/networkSecurityGroups",
            finding_title="test",
        )
        azure_mock.get_recommendations.assert_called_once()

    def test_returns_empty_for_unknown_cloud(self):
        router, aws_mock, azure_mock = self._make_router()
        result = router.get_recommendations(
            cloud="gcp",
            rule_id="GCP-001",
            resource_type="compute.googleapis.com/Firewall",
            finding_title="test",
        )
        assert result == []
        aws_mock.get_recommendations.assert_not_called()
        azure_mock.get_recommendations.assert_not_called()

    def test_returns_empty_on_client_exception(self):
        aws_mock = MagicMock()
        aws_mock.get_recommendations.side_effect = RuntimeError("connection lost")
        router = MCPRouter(aws_client=aws_mock, azure_client=MagicMock())
        result = router.get_recommendations(
            cloud="aws",
            rule_id="AWS-NET-001",
            resource_type="AWS::EC2::VPC",
            finding_title="test",
        )
        assert result == []

    def test_cloud_param_case_insensitive(self):
        router, aws_mock, azure_mock = self._make_router()
        router.get_recommendations(
            cloud="AWS",
            rule_id="AWS-NET-001",
            resource_type="AWS::EC2::VPC",
            finding_title="test",
        )
        aws_mock.get_recommendations.assert_called_once()
