"""SSE channel manager — in-memory pub/sub for ingestion progress events.

Each creator has at most one logical channel ("ingestion:{creator_id}"). Any
number of subscribers can attach (e.g., one browser tab is the usual case).

KNOWN LIMITATION (Month 2): in-memory only. If the FastAPI instance restarts
mid-ingestion, active SSE subscribers are dropped. The frontend handles this
by reconnecting via EventSource and re-fetching state with
`GET /ingestion/status/{job_id}`. For multi-instance / horizontal scaling,
swap this module for Redis Pub/Sub.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator, Dict, List

logger = logging.getLogger(__name__)

# Maps "ingestion:{creator_id}" → list of subscriber queues.
_channels: Dict[str, List[asyncio.Queue]] = defaultdict(list)


def _channel_key(creator_id: str) -> str:
    return f"ingestion:{creator_id}"


async def publish_sse_event(creator_id: str, event_data: dict) -> None:
    """Push an event to every subscriber on this creator's channel."""
    for queue in list(_channels.get(_channel_key(creator_id), [])):
        try:
            await queue.put(event_data)
        except Exception as exc:
            logger.warning("Failed to deliver SSE event to subscriber: %s", exc)


# Events that should terminate the SSE stream (the client got what it came for).
_TERMINAL_EVENTS = {"gate_complete", "ingestion_error", "ingestion_complete", "audit_complete", "ingestion_failed", "ingestion_rate_limited"}


async def subscribe_sse(creator_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings for one subscriber.

    Emits a 30-second heartbeat to keep the connection alive through proxies.
    """
    key = _channel_key(creator_id)
    queue: asyncio.Queue = asyncio.Queue()
    _channels[key].append(queue)

    try:
        yield f"data: {json.dumps({'event': 'connected', 'creator_id': creator_id})}\n\n"

        while True:
            try:
                event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
                continue
            yield f"data: {json.dumps(event_data, default=str)}\n\n"
            if event_data.get("event") in _TERMINAL_EVENTS:
                break
    finally:
        try:
            _channels[key].remove(queue)
        except ValueError:
            pass
        if not _channels.get(key):
            _channels.pop(key, None)
