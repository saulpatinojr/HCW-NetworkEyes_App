"""Diagram file naming convention — closes Phase B Gap 9.

Convention:
  {engagement_id}-{platform}-{diagram_type}-{scope_slug}-{region}.{ext}

Examples:
  acme-20260305-a3f2-aws-vpc-topology-123456789012-us-east-1.drawio
  acme-20260305-a3f2-azure-vnet-topology-sub-a1b2c3d4.drawio
  acme-20260305-a3f2-aws-tgw-topology-tgw-0abc1234-us-west-2.svg
  acme-20260305-a3f2-aws-account-hierarchy.mmd

Rules:
  - All lowercase
  - Hyphens only (no underscores, no spaces)
  - Engagement ID is always the prefix
  - Extension is always explicit (.drawio | .svg | .png | .pdf | .mmd)
  - Max 120 chars total (filesystem safe)
"""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^a-z0-9\-]")
_MULTI_HYPHEN = re.compile(r"-{2,}")


def _slug(text: str, max_len: int = 24) -> str:
    """Lowercase, hyphenate, strip unsafe chars, truncate."""
    s = text.lower().replace("_", "-").replace("/", "-").replace(" ", "-")
    s = _UNSAFE.sub("", s)
    s = _MULTI_HYPHEN.sub("-", s)
    return s.strip("-")[:max_len]


def diagram_filename(  # noqa: PLR0913
    engagement_id: str,
    platform: str,  # "aws" | "azure"
    diagram_type: str,  # "vpc-topology" | "vnet-topology" | "tgw-topology" | etc.
    scope: str = "",  # account_id | subscription_id | tgw_id
    region: str = "",  # us-east-1 | eastus | etc.
    ext: str = ".drawio",  # .drawio | .svg | .png | .pdf | .mmd
) -> str:
    """Produce a canonical diagram filename.

    Args:
        engagement_id: From EngagementStore (e.g. 'acme-20260305-a3f2').
        platform: 'aws' or 'azure'.
        diagram_type: Diagram category (e.g. 'vpc-topology').
        scope: Account/subscription/resource identifier.
        region: AWS region or Azure location. Empty for global diagrams.
        ext: File extension including leading dot.

    Returns:
        Filename string (not a full path).
    """
    parts = [
        _slug(engagement_id, 32),
        _slug(platform, 8),
        _slug(diagram_type, 24),
    ]
    if scope:
        parts.append(_slug(scope, 20))
    if region:
        parts.append(_slug(region, 16))

    name = "-".join(p for p in parts if p)
    # Enforce max length before extension
    max_stem = 116  # 120 - 4 chars for extension
    if len(name) > max_stem:
        name = name[:max_stem].rstrip("-")

    return f"{name}{ext}"
