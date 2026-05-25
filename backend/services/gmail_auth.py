"""Gmail OAuth token management — placeholder for Session 2.

In Session 2, this module will:
- Initiate Gmail OAuth using GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET
- Receive the callback, exchange code for tokens
- Store refresh_token in Google Secret Manager under path:
    projects/{project}/secrets/threadcomb-gmail-{creator_id}/versions/latest
- Record only the Secret Manager path on creators.gmail_secret_path
- Wire up Gmail watch / push notifications

For Session 1 we provide a stub that the onboarding flow can call to mark
gmail_connected=True without actually performing OAuth. The UI button in
step-4-connect ships as a mocked button.
"""

from typing import Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def build_secret_path(creator_id: str, project: Optional[str] = None) -> str:
    """Return the canonical Secret Manager path for this creator's Gmail token."""
    project = project or "threadcomb"
    return f"projects/{project}/secrets/threadcomb-gmail-{creator_id}/versions/latest"


async def store_refresh_token_stub(creator_id: str, refresh_token: str) -> str:
    """SESSION 2 placeholder. Will write to Google Secret Manager.

    For Session 1 just log and return the would-be path. The real token is never
    persisted in Session 1 because Gmail OAuth is mocked.
    """
    path = build_secret_path(creator_id)
    logger.info(
        "[Session 1 stub] Would store Gmail refresh token for creator=%s at %s",
        creator_id,
        path,
    )
    return path
