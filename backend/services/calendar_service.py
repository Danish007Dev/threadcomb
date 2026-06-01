# backend/services/calendar_service.py

import asyncio
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


async def create_followup_event(
    creator_id: str,
    title: str,
    date: datetime,
    description: str = "",
) -> str:
    """
    Creates a Google Calendar event as a follow-up reminder.
    Returns the event ID.
    """
    from services.gmail_auth import get_gmail_credentials
    # Calendar uses same OAuth credentials as Gmail if scope includes calendar.events
    credentials = await get_gmail_credentials(creator_id)
    service = build("calendar", "v3", credentials=credentials)

    event = {
        "summary": title,
        "description": description,
        "start": {
            "date": date.strftime("%Y-%m-%d"),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "date": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 480},  # 8 hours before
            ],
        },
    }

    created = await asyncio.to_thread(
        lambda: service.events().insert(
            calendarId="primary",
            body=event,
        ).execute()
    )

    logger.info(f"Calendar event created: {created['id']} for creator {creator_id}")
    return created["id"]
