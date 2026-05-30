"""Gmail watch registration helper (Session 2B)."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


async def register_gmail_watch(
    credentials,
    topic_name: str,
    label_ids: Optional[list[str]] = None,
    label_filter_action: str = "include",
) -> dict:
    """Register a Gmail watch on the authenticated user's mailbox.

    Returns history_id, expiration (datetime), and email_address.
    All .execute() calls are wrapped in asyncio.to_thread().
    """
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    body = {"topicName": topic_name}
    if label_ids:
        body["labelIds"] = label_ids
        body["labelFilterAction"] = label_filter_action

    try:
        result = await asyncio.to_thread(
            lambda: service.users().watch(userId="me", body=body).execute()
        )
    except HttpError as exc:
        logger.error("Gmail watch registration failed: %s", exc)
        raise

    expiration = None
    expiration_ms = result.get("expiration")
    if expiration_ms:
        try:
            expiration = datetime.fromtimestamp(int(expiration_ms) / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            expiration = None

    return {
        "history_id": result.get("historyId"),
        "expiration": expiration,
        "email_address": result.get("emailAddress"),
    }
