"""Gmail fetch helpers.

All synchronous googleapiclient .execute() calls are wrapped in
asyncio.to_thread() to keep the FastAPI event loop unblocked.
"""

import asyncio
import logging
from typing import List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


DEAL_SIGNAL_QUERY = (
    "(collaboration OR partnership OR collab OR sponsorship OR invoice OR contract OR "
    '"brand deal" OR "paid partnership" OR gifted OR gifting OR "media kit" OR '
    '"rate card" OR "per post" OR "per reel" OR "per video" OR deliverable OR '
    "integrate OR integration) newer_than:180d"
)

THREAD_FETCH_RATE_LIMIT_SECONDS = 1.0
MAX_THREADS_PER_FULL_INGEST = 600
MAX_THREAD_CHARS = 16000


async def fetch_thread_ids(
    credentials,
    query: str = DEAL_SIGNAL_QUERY,
    max_results: int = MAX_THREADS_PER_FULL_INGEST,
) -> Tuple[List[str], int]:
    """Fetch thread IDs matching a Gmail query, paginated.

    Returns (thread_ids, total_estimate).
    """
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    thread_ids: List[str] = []
    page_token: Optional[str] = None

    while True:
        try:
            params = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token

            # REQUIRED: asyncio.to_thread wraps synchronous .execute()
            result = await asyncio.to_thread(
                lambda p=params: service.users().threads().list(**p).execute()
            )

            threads = result.get("threads", [])
            thread_ids.extend([t["id"] for t in threads])
            page_token = result.get("nextPageToken")

            if not page_token or len(thread_ids) >= max_results:
                break
            await asyncio.sleep(0.2)
        except HttpError as exc:
            if exc.resp.status == 429:
                logger.warning("Gmail rate limited. Waiting 5s.")
                await asyncio.sleep(5)
                continue
            if exc.resp.status == 401:
                raise ValueError("Gmail token expired. Re-authentication required.")
            logger.error("Gmail API error: %s", exc)
            raise

    return thread_ids[:max_results], len(thread_ids)


async def fetch_thread_content(credentials, thread_id: str) -> Optional[dict]:
    """Fetch one thread's full content. Returns None on any error."""
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    try:
        # REQUIRED: asyncio.to_thread wraps synchronous .execute()
        return await asyncio.to_thread(
            lambda: service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
    except HttpError as exc:
        logger.warning("Failed to fetch thread %s: %s", thread_id, exc)
        return None


async def fetch_history_delta(
    credentials, start_history_id: str
) -> Tuple[List[str], str]:
    """Delta-fetch for incremental ingestion (Gmail push webhook).

    Returns (new_thread_ids, new_history_id). Raises ``ValueError`` with the
    message ``HISTORY_ID_EXPIRED`` if the history pointer is stale.
    """
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    new_thread_ids: List[str] = []

    try:
        # REQUIRED: asyncio.to_thread wraps synchronous .execute()
        result = await asyncio.to_thread(
            lambda: service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            )
            .execute()
        )

        for record in result.get("history", []):
            for msg in record.get("messagesAdded", []):
                tid = msg.get("message", {}).get("threadId")
                if tid and tid not in new_thread_ids:
                    new_thread_ids.append(tid)

        new_history_id = result.get("historyId", start_history_id)
        return new_thread_ids, new_history_id
    except HttpError as exc:
        if exc.resp.status == 404:
            raise ValueError("HISTORY_ID_EXPIRED")
        raise
