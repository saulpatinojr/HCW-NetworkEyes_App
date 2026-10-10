"""Engagement model — central state for an assessment engagement."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class EnvironmentInventory(BaseModel):
    aws_account_ids: list[str] = Field(default_factory=list)
    aws_management_account_id: str | None = None
    azure_subscription_ids: list[str] = Field(default_factory=list)
    azure_tenant_id: str | None = None
    # Keys: us | emea | japan | other. Values: list of region strings
    aws_regions: dict = Field(default_factory=dict)
    azure_regions: dict = Field(default_factory=dict)
    known_constraints: list[str] = Field(default_factory=list)


class EngagementConfig(BaseModel):
    engagement_id: str
    client_name: str
    client_slug: str
    regions: list[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    engagement_end_date: str | None = None
    inventory: EnvironmentInventory | None = None
    modules_installed: list[str] = Field(default_factory=list)
    # DD-009: review_complete=False BLOCKS cna report
    review_complete: bool = False
    status: str = "initialized"  # initialized|discovering|analyzing|reviewing|reporting|delivered
