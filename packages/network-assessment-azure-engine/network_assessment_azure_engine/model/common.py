"""Enums shared across the topology model."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["SubnetType"]


class SubnetType(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"
