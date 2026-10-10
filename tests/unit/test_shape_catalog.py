"""Unit tests for cna.diagram_engine.shape_catalog."""

from __future__ import annotations

from cna.diagram_engine.shape_catalog import (
    ALLOWED_LIBS,
    catalog_snapshot,
    is_allowed_style,
    shape_style,
)


def test_allowed_libs_is_azure2_and_aws4():
    assert ALLOWED_LIBS == frozenset({"azure2", "aws4"})


def test_is_allowed_style_accepts_pinned_libraries():
    # AWS ships a real aws4 stencil set; Azure icons are SVG image paths.
    assert is_allowed_style("shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.vpc;")
    assert is_allowed_style("image;html=1;image=img/lib/azure2/networking/Virtual_Networks.svg;")


def test_is_allowed_style_rejects_azure2_stencil_form():
    """`shape=mxgraph.azure2.*` is not a real stencil namespace.

    draw.io renders it as a plain blue rectangle with no icon — verified
    2026-08-28 by exporting both forms with the headless CLI and comparing the
    PNGs. The catalog shipped that form until then, so every "Azure icon" in a
    generated diagram was actually a blue box. Rejecting it here is what stops
    the regression coming back.
    """
    assert not is_allowed_style("shape=mxgraph.azure2.virtual_networks;")
    assert not is_allowed_style("shape=mxgraph.azure2.firewalls;fillColor=#0078D4;")


def test_is_allowed_style_rejects_other_libraries():
    assert not is_allowed_style("shape=mxgraph.azure.virtual_networks;")  # azure (v1)
    assert not is_allowed_style("shape=mxgraph.aws3.vpc;")
    assert not is_allowed_style("shape=mxgraph.gcp2.network;")
    assert not is_allowed_style("image=img/lib/gcp2/network/vpc.svg;")
    assert not is_allowed_style("")
    assert not is_allowed_style("rounded=1;")


def test_shape_style_returns_catalog_entry():
    style = shape_style("aws4", "vpc")
    assert "mxgraph.aws4" in style


def test_shape_style_returns_default_when_missing():
    fallback = "image;html=1;image=img/lib/azure2/networking/Firewalls.svg;"
    assert shape_style("azure2", "does_not_exist", fallback) == fallback


def test_shape_style_rejects_unknown_library():
    fallback = "image;html=1;image=img/lib/azure2/networking/Firewalls.svg;"
    assert shape_style("gcp2", "anything", fallback) == fallback


def test_azure_catalog_uses_image_paths_only():
    """Guard the whole Azure table, not just the allow-list predicate."""
    azure = catalog_snapshot()["azure2"]
    assert azure, "Azure catalog must not be empty"
    for key, style in azure.items():
        assert "img/lib/azure2/" in style, f"{key} is not an Azure2 image path: {style}"
        assert "mxgraph.azure2" not in style, f"{key} still uses the blue-box stencil form"


def test_aws_catalog_uses_aws4_stencils_only():
    aws = catalog_snapshot()["aws4"]
    assert aws, "AWS catalog must not be empty"
    for key, style in aws.items():
        assert "mxgraph.aws4" in style, f"{key} is not an aws4 stencil: {style}"


def test_catalog_covers_the_resources_the_generator_draws():
    """The generator's service band asks for these keys by name."""
    azure = catalog_snapshot()["azure2"]
    required = {
        "firewall",
        "vnet_gateway",
        "expressroute",
        "vwan",
        "application_gateway",
        "load_balancer",
        "waf_policy",
        "bastion",
        "nat_gateway",
        "private_endpoint",
        "private_dns_zone",
        "public_ip",
    }
    assert required <= set(azure), f"missing: {sorted(required - set(azure))}"


def test_catalog_snapshot_only_pinned_libraries():
    snap = catalog_snapshot()
    assert set(snap.keys()) == {"azure2", "aws4"}
    for lib, table in snap.items():
        for key, style in table.items():
            assert is_allowed_style(style), f"{lib}:{key} = {style}"
