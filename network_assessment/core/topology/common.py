"""Enums shared by the Azure and AWS topology models.

``SubnetType`` lives in the engine package (``network_assessment_azure_engine.model.common``) and is
re-exported here; ``AttachmentType`` and ``PeeringState`` are AWS-only and stay in the monorepo.
"""

from __future__ import annotations

from enum import StrEnum

from network_assessment_azure_engine.model.common import SubnetType

__all__ = [
    "AttachmentType",
    "PeeringState",
    "SubnetType",
]


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
