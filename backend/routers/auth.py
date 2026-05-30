"""Google OAuth auth endpoints for ThreadComb."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
import uuid

import requests
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from requests_oauthlib import OAuth2Session

from config import settings
from database.mongodb import get_db
from models.common import DataClassificationTier
from services.gmail_auth import store_gmail_token
from services.mongodb_writer import update_with_classification, write_with_classification

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Dev-only: allow http://localhost OAuth callback during local development.
_frontend_base = settings.FRONTEND_BASE_URL.lower()
_redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI.lower()
if _frontend_base.startswith("http://localhost") or _redirect_uri.startswith("http://localhost"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    logger.info("OAuth dev mode: allowing insecure transport for localhost")


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
    google_sub: Optional[str] = None
    email: str
    name: str
    avatar_url: Optional[str] = None


class SessionExchangeInput(BaseModel):
    session_id: str


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


def _default_next_url() -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/callback"


def _normalize_next_url(next_url: Optional[str]) -> str:
    fallback = _default_next_url()
    if not next_url:
        return fallback
    if next_url.startswith("/"):
        return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{next_url}"
    parsed = urlparse(next_url)
    allowed_base = urlparse(settings.FRONTEND_BASE_URL)
    if parsed.scheme in {"http", "https"} and parsed.netloc == allowed_base.netloc:
        return next_url
    return fallback


def _encode_state(next_url: str) -> str:
    payload = {"next": _normalize_next_url(next_url), "nonce": secrets.token_urlsafe(16)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_state(state: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {"next": _default_next_url()}


async def _upsert_creator_from_google_user(
    email: str,
    name: str,
    avatar_url: Optional[str],
    google_sub: Optional[str] = None,
) -> dict:
    db = get_db()
    existing = await db.creators.find_one({"email": email}, {"_id": 0})
    if existing:
        await update_with_classification(
            db.creators,
            {"creator_id": existing["creator_id"]},
            {
                "name": name or existing.get("name", ""),
                "avatar_url": avatar_url or existing.get("avatar_url"),
                "google_sub": google_sub or existing.get("google_sub"),
            },
        )
        return await db.creators.find_one({"creator_id": existing["creator_id"]}, {"_id": 0})

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


async def _create_session(creator_id: str, session_token: str, expires_at: datetime) -> None:
    db = get_db()
    await db.creator_sessions.delete_many({"session_token": session_token})
    document = {"creator_id": creator_id, "session_token": session_token, "expires_at": expires_at}
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
        secure=False,
        samesite="lax",
    )


async def get_current_creator(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    token = session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    db = get_db()
    session_doc = await db.creator_sessions.find_one({"session_token": token}, {"_id": 0})
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

    creator = await db.creators.find_one({"creator_id": session_doc["creator_id"]}, {"_id": 0})
    if not creator:
        raise HTTPException(status_code=401, detail="Creator not found")
    return creator


@router.get("/google/login")
async def google_login(next: Optional[str] = None):
    """Start the Google OAuth flow."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    state = _encode_state(next or _default_next_url())
    oauth = OAuth2Session(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        scope=GOOGLE_SCOPES,
        state=state,
    )
    auth_url, _ = oauth.authorization_url(
        GOOGLE_AUTH_URL,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    return RedirectResponse(auth_url, status_code=302)


@router.get("/google/callback")
async def google_callback(request: Request):
    """Handle Google OAuth callback, persist creator/session, then redirect back."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    params = request.query_params
    if params.get("error"):
        raise HTTPException(status_code=400, detail=params.get("error_description") or params.get("error"))

    state_payload = _decode_state(params.get("state", ""))
    next_url = _normalize_next_url(state_payload.get("next"))

    oauth = OAuth2Session(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        scope=GOOGLE_SCOPES,
        state=params.get("state", ""),
    )

    try:
        token = oauth.fetch_token(
            GOOGLE_TOKEN_URL,
            authorization_response=str(request.url),
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            include_client_id=True,
            scope=GOOGLE_SCOPES,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Google token exchange failed: %s", exc)
        raise HTTPException(status_code=401, detail="Google sign-in failed")

    try:
        userinfo_response = oauth.get(GOOGLE_USERINFO_URL, timeout=20)
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except requests.RequestException as exc:
        logger.error("Google userinfo fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="Google profile lookup failed")

    email = userinfo.get("email")
    name = userinfo.get("name") or email
    picture = userinfo.get("picture")
    google_sub = userinfo.get("id")
    if not email:
        raise HTTPException(status_code=502, detail="Google profile missing email")

    creator = await _upsert_creator_from_google_user(
        email=email,
        name=name,
        avatar_url=picture,
        google_sub=google_sub,
    )

    token_path = await store_gmail_token(creator["creator_id"], token)
    db = get_db()
    await db.creators.update_one(
        {"creator_id": creator["creator_id"]},
        {
            "$set": {
                "gmail_connected": True,
                "gmail_secret_path": token_path,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await _create_session(creator["creator_id"], session_token, expires_at)

    response = RedirectResponse(next_url, status_code=302)
    _set_session_cookie(response, session_token, max_age_seconds=7 * 24 * 60 * 60)
    return response


@router.post("/session")
async def exchange_session(_: SessionExchangeInput):
    raise HTTPException(status_code=410, detail="Use /auth/google/login for Google OAuth")


@router.get("/me")
async def me(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    creator = await get_current_creator(session_token, authorization)
    return _public_creator(creator)


@router.post("/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(default=None)):
    if session_token:
        db = get_db()
        await db.creator_sessions.delete_many({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@router.post("/creator")
async def create_or_fetch_creator(payload: CreatorCreateInputDirect):
    creator = await _upsert_creator_from_google_user(
        email=payload.email,
        name=payload.name,
        avatar_url=payload.avatar_url,
        google_sub=payload.google_sub,
    )
    return {"creator_id": creator["creator_id"], "onboarding_step": creator.get("onboarding_step", 0)}


@router.get("/creator/{creator_id}")
async def get_creator(creator_id: str):
    db = get_db()
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    creator.pop("gmail_secret_path", None)
    return creator


@router.delete("/creator/{creator_id}")
async def delete_creator(creator_id: str):
    db = get_db()
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
