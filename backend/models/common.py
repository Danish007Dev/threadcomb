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


class AgentActionType(str, Enum):
    INGESTION_STARTED = "ingestion_started"
    INGESTION_COMPLETE = "ingestion_complete"
    EXTRACTION_FAILED = "extraction_failed"
    DRAFT_GENERATED = "draft_generated"
    EMAIL_SENT = "email_sent"
    EMAIL_REJECTED = "email_rejected"
    INVOICE_UPDATED = "invoice_updated"
    REPORT_GENERATED = "report_generated"
    CALENDAR_EVENT_CREATED = "calendar_event_created"
    HITL_QUEUED = "hitl_queued"
    HITL_RESOLVED = "hitl_resolved"


class ActionResult(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING_APPROVAL = "pending_approval"
    PENDING_HITL = "pending_hitl"
