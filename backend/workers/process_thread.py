"""Cloud Tasks worker endpoint for thread extraction (Session 3 — real worker).

Also includes the dev-only trigger-direct endpoint for localhost testing.
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workers/extract-thread")
async def extract_thread_worker(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive a sanitised thread from the Cloud Tasks queue and run extraction."""
    worker_secret = request.headers.get("X-ThreadComb-Worker-Secret", "")
    if worker_secret != settings.WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker secret")

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Worker received invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    thread_id = payload.get("thread_id", "unknown")
    creator_id = payload.get("creator_id", "unknown")
    logger.info(
        "Received extraction task: thread=%s creator=%s",
        thread_id,
        creator_id,
    )

    from workers.extract_thread import run_extraction_worker
    background_tasks.add_task(run_extraction_worker, payload=payload)

    return {"status": "received", "thread_id": thread_id}


@router.post("/workers/trigger-direct")
async def trigger_extraction_direct(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    DEV ONLY — bypasses Cloud Tasks, calls extraction logic directly.
    Use this for local testing when Cloud Tasks cannot reach localhost.
    Remove or gate behind DEBUG flag before production deployment.
    Accepts same payload as /workers/extract-thread.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Only available in DEBUG mode")

    body = await request.json()

    from workers.extract_thread import run_extraction_worker
    background_tasks.add_task(run_extraction_worker, payload=body)

    return {"status": "triggered", "mode": "direct", "thread_id": body.get("thread_id")}
