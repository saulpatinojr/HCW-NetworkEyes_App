"""Unit tests for engagement model."""

from cna.core.engagement import EngagementConfig


def test_review_complete_defaults_false():
    """Review gate starts closed (DD-009)."""
    e = EngagementConfig(
        engagement_id="ENG-001",
        client_name="Acme Corp",
        client_slug="acme",
        regions=["us"],
    )
    assert e.review_complete is False


def test_status_defaults_initialized():
    e = EngagementConfig(
        engagement_id="ENG-002",
        client_name="Test",
        client_slug="test",
        regions=["us", "emea"],
    )
    assert e.status == "initialized"
