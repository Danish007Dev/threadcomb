"""Helpers for the ingestion_jobs MongoDB collection.

These functions are called from the ingestion orchestrator. They use atomic
$inc / $set updates so concurrent thread-processing loops don't race.
"""

import logging
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_job_id() -> str:
    """Return a unique 16-char job id (used for SSE channel naming, NOT _id)."""
    return str(uuid.uuid4()).replace("-", "")[:16]


def _to_object_id(job_id: str):
    """Convert a job_id string to an ObjectId, returning None if invalid."""
    try:
        return ObjectId(job_id)
    except (InvalidId, TypeError):
        return None


async def increment_job_counter(db, job_id: str, field: str, amount: int = 1) -> None:
    """Atomically increment a counter field on an ingestion_jobs document.

    Valid fields: threads_fetched, threads_passed_gate, threads_failed_gate,
    threads_low_confidence, threads_queued_for_extraction,
    threads_extraction_complete, threads_errored.
    """
    valid_fields = {
        "threads_fetched",
        "threads_passed_gate",
        "threads_failed_gate",
        "threads_low_confidence",
        "threads_queued_for_extraction",
        "threads_extraction_complete",
        "threads_errored",
    }
    if field not in valid_fields:
        logger.warning("increment_job_counter called with unknown field: %s", field)
        return

    oid = _to_object_id(job_id)
    if oid is None:
        logger.warning("increment_job_counter: invalid job_id %s", job_id)
        return

    await db.ingestion_jobs.update_one(
        {"_id": oid},
        {"$inc": {field: amount}, "$set": {"updated_at": _utcnow()}},
    )


async def update_job_status(
    db,
    job_id: str,
    status,  # IngestionStatus enum value
    error_message: str = None,
) -> None:
    """Update the status field on an ingestion_jobs document.

    Sets `started_at` on first move from PENDING into FETCHING.
    Sets `completed_at` and `duration_seconds` on terminal states.
    """
    from models.ingestion import IngestionStatus

    oid = _to_object_id(job_id)
    if oid is None:
        logger.warning("update_job_status: invalid job_id %s", job_id)
        return

    update = {
        "status": status.value if hasattr(status, "value") else str(status),
        "updated_at": _utcnow(),
    }

    if status == IngestionStatus.FETCHING:
        update["started_at"] = _utcnow()

    if status in (
        IngestionStatus.COMPLETE,
        IngestionStatus.FAILED,
        IngestionStatus.PARTIAL,
        IngestionStatus.QUEUED_FOR_EXTRACTION,
    ):
        update["completed_at"] = _utcnow()

    if error_message:
        update["error_message"] = error_message

    # Compute duration if started_at is recorded.
    job = await db.ingestion_jobs.find_one({"_id": oid}, {"started_at": 1})
    if (
        job
        and job.get("started_at")
        and status
        in (
            IngestionStatus.COMPLETE,
            IngestionStatus.FAILED,
            IngestionStatus.PARTIAL,
            IngestionStatus.QUEUED_FOR_EXTRACTION,
        )
    ):
        started = job["started_at"]
        if isinstance(started, str):
            try:
                started = datetime.fromisoformat(started)
            except ValueError:
                started = None
        if started:
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            duration = (_utcnow() - started).total_seconds()
            update["duration_seconds"] = round(duration, 1)

    await db.ingestion_jobs.update_one({"_id": oid}, {"$set": update})
