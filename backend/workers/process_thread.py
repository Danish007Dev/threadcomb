"""Cloud Tasks worker endpoint for thread extraction (Session 2B stub)."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workers/extract-thread")
async def extract_thread_worker(request: Request):
    """Receive a sanitised thread from the Cloud Tasks queue (stub)."""
    worker_secret = request.headers.get("X-ThreadComb-Worker-Secret", "")
    if worker_secret != settings.WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker secret")

    body = await request.body()
    try:
        payload = json.loads(body)
        thread_id = payload.get("thread_id", "unknown")
        creator_id = payload.get("creator_id", "unknown")
        logger.info(
            "[STUB] Received extraction task: thread=%s creator=%s",
            thread_id,
            creator_id,
        )
    except json.JSONDecodeError:
        logger.error("Worker received invalid JSON payload")

    return {"status": "received", "note": "Extraction pipeline not yet built"}
