"""Auth endpoints — Emergent-managed Google login.

Flow (per Emergent Auth playbook):
  1. Frontend redirects user to https://auth.emergentagent.com/?redirect=<url>
  2. Google completes OAuth; user lands at <url>#session_id=<sid>
  3. Frontend POSTs the session_id here to /api/auth/session
  4. We call demobackend.emergentagent.com/auth/v1/env/oauth/session-data
  5. We upsert the creator, create a creator_sessions record, set httpOnly cookie
  6. Subsequent requests use the cookie (or Authorization header) to identify the creator

Important: raw Gmail tokens are never stored here. Only the session_token issued
by Emergent Auth, which represents creator identity, is persisted in
creator_sessions.
"""

from fastapi import APIRouter, HTTPException, Request, Response, Cookie, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging
import httpx

from database.mongodb import get_db
from services.mongodb_writer import (
    write_with_classification,
    update_with_classification,
)
from models.common import DataClassificationTier
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SessionExchangeInput(BaseModel):
    session_id: str


class CreatorPublic(BaseModel):
    creator_id: str
    email: str
    name: str
    avatar_url: Optional[str] = None
    onboarding_step: int
    onboarding_completed_at: Optional[str] = None
    platform_primary: Optional[str] = None
    niche: Optional[str] = None
    gmail_connected: bool = False


class CreatorCreateInputDirect(BaseModel):
    """Used by the /auth/creator endpoint per spec — direct (non-OAuth) creation.
    Real flow uses /auth/session via Emergent Auth."""

    google_sub: Optional[str] = None
    email: str
    name: str
    avatar_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def _public_creator(doc: dict) -> dict:
    completed = doc.get("onboarding_completed_at")
    if isinstance(completed, datetime):
        completed = completed.isoformat()
    return {
        "creator_id": doc["creator_id"],
        "email": doc["email"],
        "name": doc.get("name", ""),
        "avatar_url": doc.get("avatar_url"),
        "onboarding_step": doc.get("onboarding_step", 0),
        "onboarding_completed_at": completed,
        "platform_primary": doc.get("platform_primary"),
        "niche": doc.get("niche"),
        "gmail_connected": doc.get("gmail_connected", False),
    }


async def _upsert_creator_from_oauth(
    email: str,
    name: str,
    avatar_url: Optional[str],
    google_sub: Optional[str] = None,
) -> dict:
    """Find creator by email; create if missing. Returns the full creator doc."""
    db = get_db()
    existing = await db.creators.find_one({"email": email}, {"_id": 0})
    if existing:
        # Refresh display fields opportunistically.
        await update_with_classification(
            db.creators,
            {"creator_id": existing["creator_id"]},
            {
                "name": name or existing.get("name", ""),
                "avatar_url": avatar_url or existing.get("avatar_url"),
                "google_sub": google_sub or existing.get("google_sub"),
            },
        )
        return await db.creators.find_one(
            {"creator_id": existing["creator_id"]}, {"_id": 0}
        )

    creator_id = f"creator_{uuid.uuid4().hex[:12]}"
    document = {
        "creator_id": creator_id,
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "avatar_url": avatar_url,
        "handle": None,
        "platform_primary": None,
        "follower_count": None,
        "follower_tier": None,
        "niche": None,
        "niche_secondary": [],
        "geography": "IN",
        "language_primary": "en",
        "onboarding_step": 0,
        "onboarding_completed_at": None,
        "voice_profile_brand": {},
        "voice_profile_fan": {},
        "rate_benchmarks": {"currency": "INR"},
        "skills_map_version": 0,
        "gmail_connected": False,
        "gmail_watch": {"active": False},
        "gmail_secret_path": None,
        "subscription": {"plan": "free", "status": "active"},
    }
    await write_with_classification(
        db.creators,
        document,
        classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        anonymisation_eligible=False,
        export_eligible=True,
    )
    logger.info("Created creator %s for email=%s", creator_id, email)
    return await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})


async def _create_session(
    creator_id: str, session_token: str, expires_at: datetime
) -> None:
    db = get_db()
    await db.creator_sessions.delete_many({"session_token": session_token})
    document = {
        "creator_id": creator_id,
        "session_token": session_token,
        "expires_at": expires_at,
    }
    await write_with_classification(
        db.creator_sessions,
        document,
        classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        anonymisation_eligible=False,
        export_eligible=False,
    )


def _set_session_cookie(response: Response, session_token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=max_age_seconds,
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )


async def get_current_creator(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Resolve the creator from cookie first, Authorization header as fallback."""
    token = session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    db = get_db()
    session_doc = await db.creator_sessions.find_one(
        {"session_token": token}, {"_id": 0}
    )
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            expires_at = None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    creator = await db.creators.find_one(
        {"creator_id": session_doc["creator_id"]}, {"_id": 0}
    )
    if not creator:
        raise HTTPException(status_code=401, detail="Creator not found")
    return creator


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/session")
async def exchange_session(payload: SessionExchangeInput, response: Response):
    """Exchange Emergent Auth session_id for our own session_token cookie.

    REMINDER: This call to Emergent Auth /session-data must happen from the
    backend only — never the frontend.
    """
    url = f"{settings.EMERGENT_AUTH_BASE}/session-data"
    headers = {"X-Session-ID": payload.session_id}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("Emergent Auth network error: %s", exc)
        raise HTTPException(status_code=502, detail="Auth provider unreachable")

    if r.status_code != 200:
        logger.warning("Emergent Auth session exchange failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=401, detail="Invalid session_id")

    data = r.json()
    email = data.get("email")
    name = data.get("name") or email
    picture = data.get("picture")
    google_sub = data.get("id")
    session_token = data.get("session_token")
    if not email or not session_token:
        raise HTTPException(status_code=502, detail="Malformed auth response")

    creator = await _upsert_creator_from_oauth(
        email=email, name=name, avatar_url=picture, google_sub=google_sub
    )
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await _create_session(creator["creator_id"], session_token, expires_at)
    _set_session_cookie(response, session_token, max_age_seconds=7 * 24 * 60 * 60)

    return {"creator": _public_creator(creator), "session_token": session_token}


@router.get("/me")
async def me(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    creator = await get_current_creator(session_token, authorization)
    return _public_creator(creator)


@router.post("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(default=None),
):
    if session_token:
        db = get_db()
        await db.creator_sessions.delete_many({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Spec endpoints (direct creator create / read / delete)
# ---------------------------------------------------------------------------


@router.post("/creator")
async def create_or_fetch_creator(payload: CreatorCreateInputDirect):
    """Create or fetch a creator document directly. Used by tests and tooling.

    Production OAuth flow goes through POST /auth/session instead.
    """
    creator = await _upsert_creator_from_oauth(
        email=payload.email,
        name=payload.name,
        avatar_url=payload.avatar_url,
        google_sub=payload.google_sub,
    )
    return {
        "creator_id": creator["creator_id"],
        "onboarding_step": creator.get("onboarding_step", 0),
    }


@router.get("/creator/{creator_id}")
async def get_creator(creator_id: str):
    db = get_db()
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    # Strip sensitive fields (we never store oauth tokens, but be explicit)
    creator.pop("gmail_secret_path", None)
    return creator


@router.delete("/creator/{creator_id}")
async def delete_creator(creator_id: str):
    """DPDP-compliant full data deletion. Removes creator and every related doc."""
    db = get_db()
    # Verify creator exists
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    related_collections = [
        "creators",
        "creator_sessions",
        "deals",
        "invoices",
        "skills_map",
        "agent_actions",
        "fan_interactions",
        "fan_profiles",
        "response_templates",
    ]
    deleted_counts = {}
    for name in related_collections:
        result = await db[name].delete_many({"creator_id": creator_id})
        deleted_counts[name] = result.deleted_count

    logger.info("Deleted creator %s across collections: %s", creator_id, deleted_counts)
    return {"creator_id": creator_id, "deleted_counts": deleted_counts}
