"""Enums shared by the Azure and AWS topology models.

Split out of ``cna.core.topology_schema`` so that ``cna.core.topology.azure`` and
``cna.core.topology.aws`` depend on this module and never on each other.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AttachmentType",
    "PeeringState",
    "SubnetType",
]


class SubnetType(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"


class AttachmentType(StrEnum):
    VPC = "vpc"
    VPN = "vpn"
    DIRECT_CONNECT = "direct_connect"
    PEERING = "peering"
    CONNECT = "connect"


class PeeringState(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DELETED = "deleted"
