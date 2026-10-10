"""Export pipeline: .drawio -> .svg -> .png -> .pdf

Phase B. Handles the full export chain for every generated diagram.

External dependencies (installed via Dockerfile):
  - draw.io desktop CLI (`xvfb-run drawio --export`)
    OR diagrams.net headless export server
  - cairosvg        : .svg -> .png
  - weasyprint      : .png + HTML template -> .pdf

Fallback strategy if drawio CLI not available:
  - For testing/CI: write raw .drawio XML only, skip raster export.
  - Log clearly that visual formats were not produced.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("cna.diagram_engine.export_pipeline")


class ExportPipelineError(Exception):
    """Raised when an export step fails non-recoverable."""


class DiagramExporter:
    """Orchestrates the full export chain for a single diagram.

    Usage:
        exporter = DiagramExporter(output_dir=Path("output/diagrams/acme/us"))
        paths = exporter.export(xml_string, diagram_name="vpc-topology")
        # paths: {'.drawio': Path, '.svg': Path, '.png': Path, '.pdf': Path}
    """

    DRAWIO_CLI_CANDIDATES = [
        "drawio",
        "/usr/bin/drawio",
        "/Applications/draw.io.app/Contents/MacOS/draw.io",
    ]

    def __init__(self, output_dir: Path, skip_raster: bool = False):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.skip_raster = skip_raster
        self._drawio_bin: str | None = self._find_drawio_cli()
        if not self._drawio_bin:
            logger.warning(
                "draw.io CLI not found. Only .drawio XML will be written. "
                "Install draw.io desktop or run inside the Docker container."
            )

    def _find_drawio_cli(self) -> str | None:
        for candidate in self.DRAWIO_CLI_CANDIDATES:
            if shutil.which(candidate):
                return candidate
        return None

    def export(self, xml: str, diagram_name: str) -> dict[str, Path]:
        """Run the full export chain. Always writes .drawio. Others if CLI available.

        Args:
            xml: draw.io XML string from drawio_generator.
            diagram_name: Filename stem (e.g. 'vpc-topology-us-east-1').

        Returns:
            Dict mapping format string to output Path.
        """
        if not xml or not xml.strip():
            raise ExportPipelineError(f"Empty XML string for diagram '{diagram_name}'")

        # Validate XML well-formedness before touching the filesystem
        import xml.etree.ElementTree as ET

        try:
            ET.fromstring(xml.strip())  # noqa: S314 — internal XML, not user input
        except ET.ParseError as exc:
            raise ExportPipelineError(f"malformed XML for diagram '{diagram_name}': {exc}") from exc

        # Sanitize name for filesystem
        safe_name = diagram_name.replace(" ", "-").replace("/", "_").replace("\\", "_")
        paths: dict[str, Path] = {}

        # Always write source .drawio
        drawio_path = self.output_dir / f"{safe_name}.drawio"
        drawio_path.write_text(xml, encoding="utf-8")
        paths[".drawio"] = drawio_path
        logger.info("Written: %s", drawio_path)

        if self.skip_raster or not self._drawio_bin:
            return paths

        # Export SVG via draw.io CLI
        svg_path = self.output_dir / f"{safe_name}.svg"
        try:
            self._run_drawio_export(drawio_path, svg_path, fmt="svg")
            paths[".svg"] = svg_path
        except ExportPipelineError as e:
            logger.error("SVG export failed: %s", e)
            return paths

        # SVG -> PNG via cairosvg
        png_path = self.output_dir / f"{safe_name}.png"
        try:
            import cairosvg

            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(png_path),
                scale=2.0,  # 2x for high-DPI presentations
            )
            paths[".png"] = png_path
            logger.info("Written: %s", png_path)
        except (ImportError, OSError):
            logger.warning("cairosvg not installed — skipping .png export.")
        except Exception as e:
            logger.error("PNG export failed: %s", e)

        # PNG -> PDF via weasyprint HTML wrapper
        pdf_path = self.output_dir / f"{safe_name}.pdf"
        if ".png" in paths:
            try:
                self._png_to_pdf(paths[".png"], pdf_path, title=diagram_name)
                paths[".pdf"] = pdf_path
            except Exception as e:
                logger.error("PDF export failed: %s", e)

        return paths

    def _run_drawio_export(self, drawio_path: Path, out_path: Path, fmt: str) -> None:
        """Invoke draw.io CLI headless export."""
        if self._drawio_bin is None:
            # Callers gate on `not self._drawio_bin`; reaching here without one
            # is a programming error, not a missing-CLI condition.
            raise ExportPipelineError(
                "draw.io CLI unavailable — _run_drawio_export called without a binary."
            )
        cmd = [
            self._drawio_bin,
            "--export",
            "--format",
            fmt,
            "--output",
            str(out_path),
            str(drawio_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise ExportPipelineError(
                f"draw.io export failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        logger.info("Written: %s", out_path)

    def _png_to_pdf(self, png_path: Path, pdf_path: Path, title: str) -> None:
        """Wrap PNG in an HTML page and print to PDF via weasyprint."""
        try:
            from weasyprint import HTML
        except (ImportError, OSError):
            logger.warning("weasyprint not installed — skipping .pdf export.")
            return

        html_content = f"""
        <!DOCTYPE html>
        <html><head><title>{title}</title>
        <style>
          @page {{ margin: 1cm; size: A3 landscape; }}
          body {{ margin: 0; padding: 0; }}
          img {{ max-width: 100%; height: auto; display: block; }}
        </style>
        </head><body>
        <img src="file://{png_path.absolute()}" alt="{title}"/>
        </body></html>
        """
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name

        HTML(filename=tmp_path).write_pdf(str(pdf_path))
        Path(tmp_path).unlink(missing_ok=True)
        logger.info("Written: %s", pdf_path)
