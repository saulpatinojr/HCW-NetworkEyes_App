"""``report.json``: the findings report with its rules and model versions, camelCase keys."""

from __future__ import annotations

import json

from network_assessment_azure_engine.findings.schema import FindingsReport


def report_document(report: FindingsReport) -> dict:
    """The report as a JSON-ready document (``rulesVersion`` and ``modelVersion`` at the top)."""
    return report.model_dump(mode="json", by_alias=True)


def render_json(report: FindingsReport, *, indent: int | None = 2) -> str:
    return json.dumps(report_document(report), indent=indent, ensure_ascii=False, sort_keys=False)
