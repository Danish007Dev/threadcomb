# backend/services/gmail_sender.py

import asyncio
import base64
import logging
from email.mime.text import MIMEText
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


async def send_gmail_reply(
    creator_id: str,
    thread_id: str,
    body_text: str,
) -> str:
    """
    Sends a reply to an existing Gmail thread.
    Requires gmail.send scope — ensure this is in the OAuth consent screen.
    Returns the sent message ID.

    IMPORTANT: This is only called from /deals/approve/{deal_id}.
    ACTION_POLICY enforces that send_email ALWAYS requires creator approval.
    This function is the execution step AFTER that approval.
    """
    if thread_id.startswith("demo_"):
        logger.info(f"DEMO MODE: Bypassing real Gmail API for demo thread {thread_id}")
        await asyncio.sleep(1.5)  # Simulate network latency
        return f"mock_sent_{thread_id}"

    from services.gmail_auth import get_gmail_credentials
    credentials = await get_gmail_credentials(creator_id)
    service = build("gmail", "v1", credentials=credentials)

    # Fetch the original thread to get headers for proper reply threading
    original_thread = await asyncio.to_thread(
        lambda: service.users().threads().get(
            userId="me",
            id=thread_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "Message-ID"],
        ).execute()
    )

    messages = original_thread.get("messages", [])
    last_message = messages[-1] if messages else {}
    headers = {
        h["name"].lower(): h["value"]
        for h in last_message.get("payload", {}).get("headers", [])
    }

    # Build the MIME message with proper reply headers
    message = MIMEText(body_text, "plain", "utf-8")
    original_subject = headers.get("subject", "")
    if not original_subject.lower().startswith("re:"):
        message["Subject"] = f"Re: {original_subject}"
    else:
        message["Subject"] = original_subject
    message["To"] = headers.get("from", "")
    original_message_id = headers.get("message-id", "")
    if original_message_id:
        message["In-Reply-To"] = original_message_id
        message["References"] = original_message_id

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    sent = await asyncio.to_thread(
        lambda: service.users().messages().send(
            userId="me",
            body={
                "raw": raw_message,
                "threadId": thread_id,
            }
        ).execute()
    )

    logger.info(f"Gmail reply sent. Message ID: {sent['id']} Thread: {thread_id}")
    return sent["id"]
