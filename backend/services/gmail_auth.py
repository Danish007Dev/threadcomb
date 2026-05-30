"""Google Gmail OAuth token management.

For local development this module stores creator Gmail OAuth token JSON files
under ``settings.GMAIL_TOKEN_DIR``. The stored path is written to
``creators.gmail_secret_path`` so Gmail ingestion can re-load and refresh the
tokens later.
"""

from typing import Optional
import asyncio
import json
import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

from config import settings
from database.mongodb import get_db

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def build_secret_path(creator_id: str, project: Optional[str] = None) -> str:
    """Return the local token file path for this creator's Gmail token."""
    del project
    token_dir = Path(settings.GMAIL_TOKEN_DIR)
    return str(token_dir / f"{creator_id}.json")


async def store_refresh_token_stub(creator_id: str, refresh_token: str) -> str:
    """Backward-compatible helper for older onboarding code paths."""
    del refresh_token
    return build_secret_path(creator_id)


async def store_gmail_token(creator_id: str, token_payload: dict) -> str:
    """Persist creator Gmail OAuth tokens to a local JSON file."""
    token_path = Path(build_secret_path(creator_id))
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_payload, indent=2), encoding="utf-8")

    db = get_db()
    await db.creators.update_one(
        {"creator_id": creator_id},
        {
            "$set": {
                "gmail_connected": True,
                "gmail_secret_path": str(token_path),
                "gmail_watch.active": False,
            }
        },
    )

    logger.info("Stored Gmail token for creator %s at %s", creator_id, token_path)
    return str(token_path)


async def get_gmail_credentials(creator_id: str) -> Credentials:
    """Load Gmail OAuth credentials for a creator.

    Session 2B uses env-backed credentials for local testing. Set one of:
    - GMAIL_TOKEN_JSON: raw JSON string from Google OAuth
    - GMAIL_TOKEN_PATH: path to a token JSON file
    - GMAIL_REFRESH_TOKEN (+ GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET)
    """
    token_info = None

    db = get_db()
    creator = await db.creators.find_one({"creator_id": creator_id})
    secret_path = (creator or {}).get("gmail_secret_path")
    if secret_path and Path(secret_path).exists():
        token_info = json.loads(Path(secret_path).read_text(encoding="utf-8"))

    if token_info is None:
        token_json = os.environ.get("GMAIL_TOKEN_JSON")
        if token_json:
            try:
                token_info = json.loads(token_json)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid GMAIL_TOKEN_JSON") from exc

    if token_info is None:
        token_path = os.environ.get("GMAIL_TOKEN_PATH")
        if token_path and Path(token_path).exists():
            token_info = json.loads(Path(token_path).read_text(encoding="utf-8"))

    if token_info is None:
        refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
        if refresh_token and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
            token_info = {
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": GMAIL_SCOPES,
            }

    if token_info is None:
        raise ValueError(
            "Gmail credentials not configured. Set GMAIL_TOKEN_JSON, "
            "GMAIL_TOKEN_PATH, or GMAIL_REFRESH_TOKEN."
        )

    creds = Credentials(
        token=token_info.get("token"),
        refresh_token=token_info.get("refresh_token"),
        token_uri=token_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_info.get("client_id", settings.GOOGLE_CLIENT_ID),
        client_secret=token_info.get("client_secret", settings.GOOGLE_CLIENT_SECRET),
        scopes=token_info.get("scopes") or GMAIL_SCOPES,
    )

    if (creds.expired or not creds.valid) and creds.refresh_token:
        await asyncio.to_thread(creds.refresh, GoogleRequest())
    if not creds.valid and not creds.refresh_token:
        raise ValueError("Gmail credentials are invalid or missing refresh_token.")

    logger.info("Loaded Gmail credentials for creator %s", creator_id)
    return creds
