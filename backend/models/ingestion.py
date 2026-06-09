"""Pydantic schemas for the Gmail ingestion pipeline (Session 2B)."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestionStatus(str, Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    SANITISING = "sanitising"
    GATE_CLASSIFYING = "gate_classifying"
    QUEUED_FOR_EXTRACTION = "queued_for_extraction"
    EXTRACTION_RUNNING = "extraction_running"  # Session 3
    SYNTHESIS_RUNNING = "synthesis_running"  # Session 4
    COMPLETE = "complete"
    FAILED = "failed"
    PARTIAL = "partial"


class IngestionTask(BaseModel):
    """Represents a single thread extraction task for DLQ resilience."""
    id: str = Field(alias="_id")
    thread_id: str
    creator_id: str
    job_id: str
    status: str = "pending"  # options: pending, processing, completed, dead_letter
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    error_history: List[dict] = Field(default_factory=list)
    raw_payload: dict = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utcnow)


class IngestionTrigger(str, Enum):
    MANUAL = "manual"
    SCHEDULED_WEEKLY = "scheduled_weekly"
    GMAIL_PUSH = "gmail_push"
    INCREMENTAL = "incremental"


class GateDecision(str, Enum):
    DEAL_SIGNAL = "deal_signal"
    NOT_DEAL_SIGNAL = "not_deal_signal"
    LOW_CONFIDENCE = "low_confidence"
    SPAM_DETECTED = "spam_detected"
    HINDI_MIXED = "hindi_mixed"
    RATE_LIMITED = "rate_limited"


class ThreadJobStatus(BaseModel):
    thread_id: str
    gate_decision: Optional[GateDecision] = None
    gate_confidence: Optional[float] = None
    language_detected: Optional[str] = None
    hindi_mode: bool = False
    sanitised_token_count: Optional[int] = None
    queued_for_extraction: bool = False
    extraction_complete: bool = False
    error: Optional[str] = None


class IngestionJob(BaseModel):
    creator_id: str
    trigger: IngestionTrigger
    status: IngestionStatus = IngestionStatus.PENDING
    total_threads_found: int = 0
    threads_fetched: int = 0
    threads_passed_gate: int = 0
    threads_failed_gate: int = 0
    threads_low_confidence: int = 0
    threads_queued_for_extraction: int = 0
    threads_extraction_complete: int = 0
    threads_errored: int = 0
    threads_rate_limited: int = 0
    # NOTE: thread_statuses is an embedded array for hackathon phase.
    # TODO (Month 2): move to separate thread_job_statuses collection,
    # one document per thread, to avoid document growth at scale.
    thread_statuses: List[ThreadJobStatus] = Field(default_factory=list)
    start_history_id: Optional[str] = None
    end_history_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    sse_channel: str = ""
    error_message: Optional[str] = None
    data_classification: dict = Field(
        default_factory=lambda: {
            "tier": "aggregate",
            "deletion_policy": "on_request_30d",
            "anonymisation_eligible": False,
            "export_eligible": True,
        }
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class GateClassificationResult(BaseModel):
    thread_id: str
    is_deal_signal: bool
    is_spam: bool
    language: str
    hindi_mode: bool
    confidence: float
    gate_decision: GateDecision
    reasoning_brief: str
    tokens_used: int = 0


class SanitisedThread(BaseModel):
    """In-memory only. NEVER persisted to MongoDB.

    The sanitised_text field passes through the Cloud Tasks payload as a
    documented exception to Principle 3 (no raw email text in persistent
    storage). Justification: Cloud Tasks encrypts payloads at rest and in
    transit, tasks execute immediately and are not long-term storage, and the
    text is sanitised (PII redacted, not raw email).

    See: ACTION_POLICY named exception CLOUD_TASKS_SANITISED_TEXT_TRANSIT.
    """

    thread_id: str
    creator_id: str
    sanitised_text: str
    original_token_count: int
    sanitised_token_count: int
    sender_email: str
    sender_name: Optional[str] = None
    subject: str
    message_count: int
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    has_attachments: bool = False
    attachment_names: List[str] = Field(default_factory=list)
    hindi_mode: bool = False
    language: str = "en"
