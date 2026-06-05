# backend/routers/webhooks.py
"""
Webhook receivers for external push notifications.
These are alias routes that forward to the actual implementation.
Cloud Pub/Sub points to /webhooks/gmail/pubsub (set in Phase 6 of deployment).
The actual logic lives in routers/ingestion.py::gmail_push_webhook().
"""

from fastapi import APIRouter, Request, BackgroundTasks
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhooks/gmail/pubsub")
async def gmail_pubsub_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Receives Gmail push notifications from Google Pub/Sub.
    This is the endpoint URL registered in the Pub/Sub push subscription.
    Forwards to the ingestion router's implementation.

    Always returns 200 — Pub/Sub retries on any non-200 response.
    Duplicate delivery is handled by idempotent ingestion logic.
    """
    from routers.ingestion import gmail_push_webhook as _gmail_push_webhook
    return await _gmail_push_webhook(request=request, background_tasks=background_tasks)
