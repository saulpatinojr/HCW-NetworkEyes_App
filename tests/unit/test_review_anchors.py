"""Every in-page link in ``REVIEW.md`` points at a heading that exists.

``REVIEW.md`` opens with an index whose rows link to the sections below with GitHub's heading anchors. When a heading is
renamed (the rename of the short code name changed several), the link text is easy to update and the anchor is easy to
miss, and nothing else catches it. This test builds GitHub's anchor for every heading and checks each ``](#...)`` link.

GitHub's rule: lower-case the heading, drop everything that is not a letter, a digit, a space, a hyphen or an underscore,
and turn each space into a hyphen; a heading repeated in the file gets ``-1``, ``-2`` ... on the later ones.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$", re.MULTILINE)
_LINK = re.compile(r"\]\(#(?P<anchor>[^)\s]+)\)")


def github_anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for match in _HEADING.finditer(text):
        base = re.sub(r"[^\w\- ]", "", match.group("title").lower()).replace(" ", "-")
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def test_every_in_page_link_in_review_md_names_an_existing_heading() -> None:
    text = (REPO_ROOT / "REVIEW.md").read_text(encoding="utf-8")
    anchors = github_anchors(text)
    assert len(anchors) > 20, "the heading scan found too few headings"
    missing = sorted({m.group("anchor") for m in _LINK.finditer(text)} - anchors)
    assert not missing, f"REVIEW.md links to headings that do not exist: {missing}"


def test_the_anchor_rule_matches_what_github_makes_of_the_renamed_headings() -> None:
    text = (
        "## R-016 — Retire `apps/network-assessment-worker` and its image\n\n## Same\n\n## Same\n"
    )
    assert github_anchors(text) == {
        "r-016--retire-appsnetwork-assessment-worker-and-its-image",
        "same",
        "same-1",
    }
