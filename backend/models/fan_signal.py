"""Fan signal model — lightweight fan detection from Gmail (Session 3).

This is a simplified version of fan_interactions — built from Gmail data,
not Instagram API. Full fan management comes in Phase 2.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class FanSignalFromGmail(BaseModel):
    """Lightweight fan signal detected during Gmail ingestion gate pass."""
    creator_id: str
    signal_type: str          # "fan_appreciation" | "content_request" | "creator_collab" | "general"
    sender_email_hash: str    # SHA-256 hash — never store raw fan email addresses (DPDP compliance)
    subject_preview: str      # first 60 chars of subject only
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "gmail"
    data_classification: dict = Field(default_factory=lambda: {
        "tier": "personal_identifiable",
        "deletion_policy": "on_request_30d",
    })
