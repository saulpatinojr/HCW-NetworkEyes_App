"""Unit tests for cna.ai_engine.mcp_client.drawio_mcp_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cna.ai_engine.mcp_client.drawio_mcp_client import (
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
    with patch("cna.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.return_value = _fake_response(hits_payload)
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        out = client.search_shapes("vnet")
    assert len(out) == 1
    assert out[0].name == "VNet"


def test_search_shapes_returns_empty_on_network_error():
    with patch("cna.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.side_effect = RuntimeError("connection refused")
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        assert client.search_shapes("vpc") == []


def test_search_shapes_empty_query_returns_empty_without_call():
    with patch("cna.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
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
        "embedUrl": "https://viewer.diagrams.net/?embed=1",
    }
    with patch("cna.ai_engine.mcp_client.drawio_mcp_client.httpx.post") as m:
        m.return_value = _fake_response(payload)
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        out = client.create_diagram(xml, name="demo")
    assert out is not None
    assert out.name == "demo"
    assert out.embed_url.startswith("https://viewer.diagrams.net/")


def test_health_handles_failure_gracefully():
    with patch("cna.ai_engine.mcp_client.drawio_mcp_client.httpx.get") as m:
        m.side_effect = RuntimeError("boom")
        client = DrawioMCPClient(base_url="http://test/api/drawio-mcp")
        assert client.health() is False
