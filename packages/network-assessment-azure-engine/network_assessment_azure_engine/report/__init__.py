"""Report renderers: ``render_markdown(report)`` and ``render_json(report)``."""

from network_assessment_azure_engine.report.jsonreport import render_json
from network_assessment_azure_engine.report.markdown import render_markdown

__all__ = ["render_json", "render_markdown"]
