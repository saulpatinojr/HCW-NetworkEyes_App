"""Unit tests for cna.core.diagram_naming."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cna.core.diagram_naming import (
    DIAGRAM_TYPES,
    OUTPUT_FORMATS,
    all_format_paths,
    diagram_filename,
    diagram_version_from_existing,
)

# ── diagram_filename ───────────────────────────────────────────────────────────


class TestDiagramFilename:
    def test_canonical_path_structure(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
        )
        # output/diagrams/<slug>/<region_group>/<filename>
        assert str(path).startswith(str(Path("output") / "diagrams" / "acme" / "us"))

    def test_correct_filename_format(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
            version="1.0.0",
            ext="drawio",
        )
        assert path.name == "aws_vpc_topology_us-east-1_v1.0.0.drawio"

    def test_scope_slashes_sanitized(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="azure",
            diagram_type="vnet_topology",
            scope="tenant/subscription/eastus",
        )
        assert "/" not in path.name
        assert "tenant-subscription-eastus" in path.name

    def test_scope_spaces_sanitized(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="my region",
        )
        assert " " not in path.name
        assert "my_region" in path.name

    def test_invalid_diagram_type_raises(self):
        with pytest.raises(ValueError, match="Unknown diagram type"):
            diagram_filename(
                engagement_slug="acme",
                region_group="us",
                platform="aws",
                diagram_type="invalid_type",
                scope="us-east-1",
            )

    def test_invalid_ext_raises(self):
        with pytest.raises(ValueError, match="Unknown format"):
            diagram_filename(
                engagement_slug="acme",
                region_group="us",
                platform="aws",
                diagram_type="vpc_topology",
                scope="us-east-1",
                ext="xlsx",
            )

    def test_all_valid_diagram_types_accepted(self):
        for dtype in DIAGRAM_TYPES:
            path = diagram_filename(
                engagement_slug="test",
                region_group="us",
                platform="aws",
                diagram_type=dtype,
                scope="all",
            )
            assert dtype in path.name

    def test_all_valid_extensions_accepted(self):
        for ext in OUTPUT_FORMATS:
            path = diagram_filename(
                engagement_slug="test",
                region_group="us",
                platform="aws",
                diagram_type="vpc_topology",
                scope="all",
                ext=ext,
            )
            assert path.suffix == f".{ext}"

    def test_html_extension_accepted(self):
        """HTML is an extra valid format not in OUTPUT_FORMATS but explicitly allowed."""
        path = diagram_filename(
            engagement_slug="test",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="all",
            ext="html",
        )
        assert path.suffix == ".html"

    def test_default_version_is_1_0_0(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
        )
        assert "_v1.0.0." in path.name

    def test_returns_path_object(self):
        path = diagram_filename(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
        )
        assert isinstance(path, Path)


# ── all_format_paths ───────────────────────────────────────────────────────────


class TestAllFormatPaths:
    def test_returns_all_formats(self):
        paths = all_format_paths(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
        )
        assert set(paths.keys()) == set(OUTPUT_FORMATS)

    def test_all_values_are_paths(self):
        paths = all_format_paths(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="vpc_topology",
            scope="us-east-1",
        )
        for ext, path in paths.items():
            assert isinstance(path, Path)
            assert path.suffix == f".{ext}"

    def test_paths_share_same_base_name(self):
        paths = all_format_paths(
            engagement_slug="acme",
            region_group="us",
            platform="aws",
            diagram_type="account_hierarchy",
            scope="all",
        )
        stems = {p.stem for p in paths.values()}
        # All stems should be identical (same filename, just different extension)
        assert len(stems) == 1

    def test_paths_in_correct_directory(self):
        paths = all_format_paths(
            engagement_slug="client-x",
            region_group="emea",
            platform="azure",
            diagram_type="vnet_topology",
            scope="westeurope",
        )
        for path in paths.values():
            assert "client-x" in str(path)
            assert "emea" in str(path)


# ── diagram_version_from_existing ─────────────────────────────────────────────


class TestDiagramVersionFromExisting:
    def test_returns_1_0_0_when_no_existing(self, tmp_path):
        version = diagram_version_from_existing(tmp_path, "aws_vpc_topology_us-east-1")
        assert version == "1.0.0"

    def test_bumps_patch_version(self, tmp_path):
        # Create a fake existing drawio file
        (tmp_path / "aws_vpc_topology_us-east-1_v1.0.0.drawio").touch()
        with patch("cna.core.version_manager.bump_version", return_value="1.0.1") as mock_bump:
            version = diagram_version_from_existing(tmp_path, "aws_vpc_topology_us-east-1")
            mock_bump.assert_called_once_with("1.0.0", "patch")
            assert version == "1.0.1"

    def test_uses_latest_file_alphabetically(self, tmp_path):
        """Given v1.0.0 and v1.0.2, should use v1.0.2 as the base."""
        (tmp_path / "aws_vpc_topology_us-east-1_v1.0.0.drawio").touch()
        (tmp_path / "aws_vpc_topology_us-east-1_v1.0.2.drawio").touch()
        (tmp_path / "aws_vpc_topology_us-east-1_v1.0.1.drawio").touch()
        with patch("cna.core.version_manager.bump_version", return_value="1.0.3") as mock_bump:
            diagram_version_from_existing(tmp_path, "aws_vpc_topology_us-east-1")
            # sorted() means 1.0.2 is last alphabetically
            call_version = mock_bump.call_args[0][0]
            assert call_version == "1.0.2"
