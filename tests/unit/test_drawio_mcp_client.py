"""Unit tests for network_assessment.ai_engine.mcp_client.drawio_mcp_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from network_assessment.ai_engine.mcp_client.drawio_mcp_client import (
    ALLOWED_LIBS,
    DrawioMCPClient,
    _is_allowed_style,
)


def test_allowed_libs_pinned():
    assert ALLOWED_LIBS == frozenset({"azure2", "aws4"})


def test_is_allowed_style_filters():
    assert _is_allowed_style("shape=mxgraph.azure2.vnet;")
    assert _is_allowed_style("shape=mxgraph.aws4.vpc;")
    assert not _is_allowed_style("shape=mxgraph.gcp2.subnet;")
    assert not _is_allowed_style("shape=mxgraph.azure.legacy;")


def _fake_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload)
    return r


def test_search_shapes_drops_disallowed_libraries():
    hits_payload = {
        "tool": "search_shapes",
        "hits": [
            {
                "name": "VNet",
                "library": "azure2",
                "tags": ["vnet"],
                "style": "shape=mxgraph.azure2.virtual_networks;",
                "score": 100,
            },
            {
                "name": "Sneaky",
                "library": "rogue",
                "tags": [],
                "style": "shape=mxgraph.rogue.thing;",
                "score": 50,
            },
        ],
    }
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.return_value = _fake_response(hits_payload)
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        out = client.search_shapes("vnet")
    assert len(out) == 1
    assert out[0].name == "VNet"


def test_search_shapes_returns_empty_on_network_error():
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.side_effect = RuntimeError("connection refused")
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        assert client.search_shapes("vpc") == []


def test_search_shapes_empty_query_returns_empty_without_call():
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        assert client.search_shapes("   ") == []
        m.assert_not_called()


def test_create_diagram_rejects_non_drawio_payload():
    client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
    assert client.create_diagram("not xml") is None


def test_create_diagram_round_trips_xml():
    xml = "<mxfile><diagram><mxGraphModel/></diagram></mxfile>"
    payload = {
        "tool": "create_diagram",
        "xml": xml,
        "name": "demo",
        "embedUrl": "/drawio/index.html?embed=1&proto=json",
    }
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.return_value = _fake_response(payload)
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        out = client.create_diagram(xml, name="demo")
    assert out is not None
    assert out.name == "demo"
    assert out.embed_url.startswith("/drawio/")


def test_health_handles_failure_gracefully():
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.get") as m:
        m.side_effect = RuntimeError("boom")
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        assert client.health() is False


def test_requests_carry_the_shared_bearer(monkeypatch):
    """Ticket #245: the route is internal only, so every call sends NETWORK_ASSESSMENT_API_TOKEN."""
    monkeypatch.setenv("NETWORK_ASSESSMENT_API_TOKEN", "test-shared-token-not-a-secret")
    expected = {"Authorization": "Bearer test-shared-token-not-a-secret"}
    client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as post:
        post.return_value = _fake_response({"hits": []})
        client.search_shapes("vnet")
        assert post.call_args.kwargs["headers"] == expected
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.get") as get:
        get.return_value = _fake_response({"status": "ok"})
        assert client.health() is True
        assert get.call_args.kwargs["headers"] == expected


def test_no_token_sends_no_header_and_still_degrades_gracefully(monkeypatch):
    monkeypatch.delenv("NETWORK_ASSESSMENT_API_TOKEN", raising=False)
    client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
    with patch("network_assessment.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as post:
        post.side_effect = RuntimeError("401 Unauthorized")
        assert client.search_shapes("vnet") == []
        assert post.call_args.kwargs["headers"] == {}
        assert post.call_args.kwargs["timeout"] == client._timeout
