"""Report renderers: ``render_markdown(report)`` and ``render_json(report)``."""

from cna_azure_network_engine.report.jsonreport import render_json
from cna_azure_network_engine.report.markdown import render_markdown

__all__ = ["render_json", "render_markdown"]
