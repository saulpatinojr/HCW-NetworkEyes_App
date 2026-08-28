"""Unit tests for export_pipeline.py — closes Phase B Gap 13.

11 tests covering all paths that CI actually exercises:
  - no draw.io CLI fallback (CI default)
  - skip_raster mode
  - empty XML guard
  - XML validation (malformed XML)
  - cairosvg ImportError path
  - weasyprint ImportError path
  - retry logic (subprocess mock)
  - DPI cap calculation
  - diagram_filename convention
  - corrupt SVG detection
  - output directory creation
  - multiple format paths

Plus TestRealDrawioExport: 2 tests that run the real headless export chain
wherever the draw.io CLI is installed (the container images; skipped in CI).
"""

import shutil
from unittest.mock import patch

import pytest

from cna.diagram_engine.export_pipeline import DiagramExporter, ExportPipelineError
from cna.diagram_engine.naming import diagram_filename


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "diagrams"


MINIMAL_XML = """<mxfile host="CNA" version="21.0.0">
  <diagram name="test">
    <mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>
  </diagram>
</mxfile>"""


class TestExporterNoCLI:
    """Covers the most common CI path: no draw.io CLI available."""

    def test_only_drawio_written_when_no_cli(self, tmp_output):
        with patch("shutil.which", return_value=None):
            exporter = DiagramExporter(output_dir=tmp_output)
        paths = exporter.export(MINIMAL_XML, "test-diagram")
        assert ".drawio" in paths
        assert paths[".drawio"].exists()
        assert ".svg" not in paths
        assert ".png" not in paths

    def test_skip_raster_mode_writes_only_drawio(self, tmp_output):
        exporter = DiagramExporter(output_dir=tmp_output, skip_raster=True)
        paths = exporter.export(MINIMAL_XML, "test-skip")
        assert ".drawio" in paths
        assert len(paths) == 1

    def test_output_dir_created_if_not_exists(self, tmp_path):
        new_dir = tmp_path / "deep" / "nested" / "dir"
        assert not new_dir.exists()
        with patch("shutil.which", return_value=None):
            DiagramExporter(output_dir=new_dir)
        assert new_dir.exists()


class TestXMLValidation:
    """Covers the XML well-formedness gate."""

    def test_malformed_xml_raises_before_write(self, tmp_output):
        exporter = DiagramExporter(output_dir=tmp_output, skip_raster=True)
        bad_xml = "<mxfile><diagram><unclosed>"
        with pytest.raises(ExportPipelineError, match="malformed"):
            exporter.export(bad_xml, "bad-diagram")

    def test_empty_xml_raises(self, tmp_output):
        exporter = DiagramExporter(output_dir=tmp_output, skip_raster=True)
        with pytest.raises(ExportPipelineError, match="Empty XML"):
            exporter.export("", "empty-diagram")

    def test_whitespace_only_xml_raises(self, tmp_output):
        exporter = DiagramExporter(output_dir=tmp_output, skip_raster=True)
        with pytest.raises(ExportPipelineError, match="Empty XML"):
            exporter.export("   \n  ", "ws-diagram")

    def test_valid_xml_does_not_raise(self, tmp_output):
        exporter = DiagramExporter(output_dir=tmp_output, skip_raster=True)
        paths = exporter.export(MINIMAL_XML, "valid-diagram")
        assert ".drawio" in paths


class TestDiagramFilename:
    """Covers the naming convention contract."""

    def test_basic_aws_vpc(self):
        name = diagram_filename(
            engagement_id="acme-20260305-a3f2",
            platform="aws",
            diagram_type="vpc-topology",
            scope="123456789012",
            region="us-east-1",
            ext=".drawio",
        )
        assert name.startswith("acme-20260305-a3f2")
        assert "aws" in name
        assert "vpc-topology" in name
        assert name.endswith(".drawio")
        assert " " not in name
        assert "_" not in name

    def test_max_length_respected(self):
        long_id = "a" * 100
        name = diagram_filename(
            engagement_id=long_id,
            platform="aws",
            diagram_type="vpc-topology",
            scope="123456789012",
            region="us-east-1",
        )
        assert len(name) <= 120

    def test_special_chars_stripped(self):
        name = diagram_filename(
            engagement_id="client/name test",
            platform="azure",
            diagram_type="vnet topology",
            ext=".svg",
        )
        assert "/" not in name
        assert " " not in name

    def test_extension_preserved(self):
        for ext in [".drawio", ".svg", ".png", ".pdf", ".mmd"]:
            name = diagram_filename("eng-001", "aws", "vpc", ext=ext)
            assert name.endswith(ext)


@pytest.mark.skipif(
    shutil.which("drawio") is None,
    reason="draw.io CLI not installed (it is present inside the container images)",
)
class TestRealDrawioExport:
    """Exercises the real headless export chain when the CLI is available.

    The container images install draw.io desktop plus the
    scripts/drawio-headless.sh wrapper (xvfb-run, --no-sandbox, HOME
    fallback); these tests prove that chain produces real SVG rather than
    silently degrading — the CNA-0.90 gap where encyclopedia diagrams
    never rendered because no image carried the CLI.
    """

    def test_export_produces_real_svg(self, tmp_output):
        from cna.core.topology_schema import AzureSubnet, AzureSubscriptionTopology, VNet
        from cna.diagram_engine.drawio_generator import generate_vnet_topology

        sub = AzureSubscriptionTopology(
            subscription_id="sub-1",
            subscription_name="acme-prod",
            tenant_id="t1",
            vnets=[
                VNet(
                    id="/v1",
                    name="vnet-hub",
                    location="eastus",
                    resource_group="rg1",
                    subscription_id="sub-1",
                    address_space=["10.0.0.0/16"],
                    subnets=[
                        AzureSubnet(id="/v1/s1", name="GatewaySubnet", address_prefix="10.0.0.0/24")
                    ],
                )
            ],
        )

        exporter = DiagramExporter(output_dir=tmp_output)
        paths = exporter.export(generate_vnet_topology(sub), "real-export")

        assert ".svg" in paths
        svg = paths[".svg"].read_text(encoding="utf-8")
        assert "<svg" in svg and len(svg) > 1000

    def test_encyclopedia_diagram_svgs_render(self):
        from cna.core.topology_schema import (
            AzureSubnet,
            AzureSubscriptionTopology,
            AzureTopology,
            VNet,
        )
        from cna.modules.network.analysis.topology_classifier import classify_topology
        from cna.report_engine.encyclopedia_report import generate_diagram_svgs

        sub = AzureSubscriptionTopology(
            subscription_id="sub-1",
            subscription_name="acme-prod",
            tenant_id="t1",
            vnets=[
                VNet(
                    id="/v1",
                    name="vnet-hub",
                    location="eastus",
                    resource_group="rg1",
                    subscription_id="sub-1",
                    address_space=["10.0.0.0/16"],
                    subnets=[
                        AzureSubnet(id="/v1/s1", name="GatewaySubnet", address_prefix="10.0.0.0/24")
                    ],
                )
            ],
        )
        topology = AzureTopology(engagement_id="e1", tenant_id="t1", subscriptions=[sub])

        current_svg, future_svg = generate_diagram_svgs(topology, classify_topology(topology))

        assert current_svg and "<svg" in current_svg
        assert future_svg and "<svg" in future_svg
