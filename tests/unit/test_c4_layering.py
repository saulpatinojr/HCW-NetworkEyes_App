"""Unit tests for cna.diagram_engine.c4_layering."""

from __future__ import annotations

from cna.diagram_engine.c4_layering import (
    AUDIENCE_BY_LAYER,
    C4Diagram,
    C4Layer,
    build_context_xml,
    classify_existing,
)


def test_audience_mapping():
    assert AUDIENCE_BY_LAYER[C4Layer.CONTEXT] == "executive"
    assert AUDIENCE_BY_LAYER[C4Layer.CONTAINER] == "architect"
    assert AUDIENCE_BY_LAYER[C4Layer.COMPONENT] == "engineer"


def test_classify_existing_preserves_payload():
    diag = classify_existing(C4Layer.CONTAINER, "demo", "<mxfile/>")
    assert diag.layer is C4Layer.CONTAINER
    assert diag.name == "demo"
    assert diag.audience == "architect"


def test_build_context_xml_includes_system_and_children():
    xml = build_context_xml("Acme", ["AWS 111111111111 / us-east-1", "Azure sub abc"])
    assert "<mxfile" in xml and "</mxfile>" in xml
    assert "Acme" in xml
    assert "us-east-1" in xml
    assert "Azure sub abc" in xml


def test_build_context_xml_handles_no_children():
    xml = build_context_xml("Acme", [])
    assert "<mxfile" in xml
    assert "no top-level systems discovered" in xml


def test_c4_diagram_dataclass_is_immutable():
    diag = C4Diagram(layer=C4Layer.CONTEXT, name="x", xml="<mxfile/>")
    try:
        diag.name = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("C4Diagram should be frozen")
