"""Cloud Tasks producer for the Session 3 extraction worker.

The Cloud Tasks Python client is synchronous, so every call goes through
asyncio.to_thread().

For development environments where Cloud Tasks is not configured
(WORKER_BASE_URL is empty), the enqueue function logs and returns a sentinel
instead of crashing.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.cloud import tasks_v2

from config import settings

logger = logging.getLogger(__name__)

# Module-level client — created once, reused.
_tasks_client: Optional[tasks_v2.CloudTasksClient] = None


def get_tasks_client() -> tasks_v2.CloudTasksClient:
    global _tasks_client
    if _tasks_client is None:
        _tasks_client = tasks_v2.CloudTasksClient()
    return _tasks_client


async def enqueue_thread_for_extraction(
    thread_id: str,
    creator_id: str,
    job_id: str,
    sanitised_text: str,
    sender_email: str,
    subject: str,
    date_range_start: str,
    date_range_end: str,
    has_attachments: bool,
    attachment_names: list,
    hindi_mode: bool,
    language: str,
    delay_seconds: int = 0,
) -> str:
    """Enqueue a sanitised thread for the Session 3 extraction worker.

    Returns the Cloud Tasks task name on success, or a sentinel string
    starting with "dev:" when Cloud Tasks is not configured.

    NAMED EXCEPTION: sanitised_text in the payload is the documented
    CLOUD_TASKS_SANITISED_TEXT_TRANSIT exception. Cloud Tasks encrypts
    payloads at rest and in transit, tasks execute immediately, and the
    text is sanitised (PII redacted), not raw email.
    """
    payload = {
        "thread_id": thread_id,
        "creator_id": creator_id,
        "job_id": job_id,
        "sanitised_text": sanitised_text,
        "sender_email": sender_email,
        "subject": subject,
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "has_attachments": has_attachments,
        "attachment_names": attachment_names,
        "hindi_mode": hindi_mode,
        "language": language,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    }

    # Development fallback — if Cloud Tasks is not configured, skip the real
    # enqueue. Session 3 will read from the queue when it's wired up.
    if not (
        settings.GOOGLE_CLOUD_PROJECT
        and settings.WORKER_BASE_URL
        and settings.WORKER_SECRET
    ):
        logger.warning(
            "[DEV] Cloud Tasks not configured (missing GOOGLE_CLOUD_PROJECT / "
            "WORKER_BASE_URL / WORKER_SECRET) — skipping enqueue for thread %s.",
            thread_id,
        )
        return f"dev:skipped:{thread_id}"

    queue_path = (
        f"projects/{settings.GOOGLE_CLOUD_PROJECT}"
        f"/locations/{settings.GOOGLE_CLOUD_LOCATION}"
        f"/queues/{settings.CLOUD_TASKS_QUEUE_NAME}"
    )

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{settings.WORKER_BASE_URL}/workers/extract-thread",
            "headers": {
                "Content-Type": "application/json",
                "X-ThreadComb-Worker-Secret": settings.WORKER_SECRET,
            },
            "body": json.dumps(payload).encode(),
        }
    }

    if delay_seconds > 0:
        from google.protobuf import timestamp_pb2

        schedule_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(schedule_time)
        task["schedule_time"] = ts

    client = get_tasks_client()
    # REQUIRED: tasks_v2.CloudTasksClient is synchronous — wrap with to_thread.
    response = await asyncio.to_thread(
        client.create_task,
        request={"parent": queue_path, "task": task},
    )

    logger.info("Enqueued thread %s for extraction. Task: %s", thread_id, response.name)
    return response.name
