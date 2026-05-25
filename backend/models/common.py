"""Shared models — DataClassification, enums used across collections."""

from enum import Enum
from datetime import datetime
from pydantic import BaseModel


class DataClassificationTier(str, Enum):
    PERSONAL_IDENTIFIABLE = "personal_identifiable"
    ANONYMISABLE = "anonymisable"
    AGGREGATE = "aggregate"


class DataClassification(BaseModel):
    tier: DataClassificationTier = DataClassificationTier.PERSONAL_IDENTIFIABLE
    deletion_policy: str = "on_request_30d"
    anonymisation_eligible: bool = False
    export_eligible: bool = True
