"""Onboarding endpoints — PATCH /onboarding/{creator_id}/step-{1,2,3,4}.

Each endpoint saves to MongoDB before allowing the user to proceed. If the
creator leaves mid-onboarding they resume from their last completed step on
next login.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from database.mongodb import get_db
from services.mongodb_writer import update_with_classification
from services.gmail_auth import store_refresh_token_stub
from models.creator import (
    Step1Input,
    Step2Input,
    Step3Input,
    follower_bucket_to_tier,
)
from models.common import DataClassificationTier

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


async def _require_creator(creator_id: str) -> dict:
    db = get_db()
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    return creator


def _public(doc: dict) -> dict:
    completed = doc.get("onboarding_completed_at")
    if isinstance(completed, datetime):
        completed = completed.isoformat()
    return {
        "creator_id": doc["creator_id"],
        "onboarding_step": doc.get("onboarding_step", 0),
        "onboarding_completed_at": completed,
        "platform_primary": doc.get("platform_primary"),
        "niche": doc.get("niche"),
        "niche_secondary": doc.get("niche_secondary", []),
        "handle": doc.get("handle"),
        "follower_tier": doc.get("follower_tier"),
        "follower_count": doc.get("follower_count"),
        "geography": doc.get("geography"),
        "language_primary": doc.get("language_primary"),
        "gmail_connected": doc.get("gmail_connected", False),
    }


@router.patch("/{creator_id}/step-1")
async def step_1_platform(creator_id: str, payload: Step1Input):
    await _require_creator(creator_id)
    db = get_db()
    await update_with_classification(
        db.creators,
        {"creator_id": creator_id},
        {
            "platform_primary": payload.platform.value,
            "onboarding_step": 1,
        },
    )
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    return _public(creator)


@router.patch("/{creator_id}/step-2")
async def step_2_niche(creator_id: str, payload: Step2Input):
    await _require_creator(creator_id)
    # Defensive: only keep secondary niches not equal to primary
    secondary = [n for n in payload.niche_secondary if n and n != payload.niche.value]
    if len(secondary) > 2:
        secondary = secondary[:2]

    db = get_db()
    await update_with_classification(
        db.creators,
        {"creator_id": creator_id},
        {
            "niche": payload.niche.value,
            "niche_secondary": secondary,
            "onboarding_step": 2,
        },
    )
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    return _public(creator)


@router.patch("/{creator_id}/step-3")
async def step_3_profile(creator_id: str, payload: Step3Input):
    await _require_creator(creator_id)
    tier = follower_bucket_to_tier(payload.follower_bucket).value

    # Approximate midpoint follower counts per bucket (used for downstream analytics)
    midpoint = {
        "under_10k": 5000,
        "10k_50k": 25000,
        "50k_200k": 100000,
        "200k_1m": 500000,
        "over_1m": 2000000,
    }
    db = get_db()
    await update_with_classification(
        db.creators,
        {"creator_id": creator_id},
        {
            "handle": payload.handle,
            "follower_count": midpoint.get(payload.follower_bucket.value, None),
            "follower_tier": tier,
            "geography": payload.geography,
            "language_primary": payload.language_primary,
            "onboarding_step": 3,
        },
    )
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    return _public(creator)


@router.post("/{creator_id}/gmail-connect")
async def step_4_gmail_connect(creator_id: str):
    """Session 1: mocked Gmail connect.

    Marks gmail_connected=True, completes onboarding, starts pilot timer.
    The real Gmail OAuth handshake ships in Session 2.
    """
    await _require_creator(creator_id)
    db = get_db()
    now = datetime.now(timezone.utc)

    secret_path = await store_refresh_token_stub(creator_id, refresh_token="MOCKED")

    await update_with_classification(
        db.creators,
        {"creator_id": creator_id},
        {
            "gmail_connected": True,
            "gmail_secret_path": secret_path,
            "gmail_watch": {"active": False},
            "onboarding_step": 5,
            "onboarding_completed_at": now,
            "subscription.pilot_started_at": now,
        },
    )
    creator = await db.creators.find_one({"creator_id": creator_id}, {"_id": 0})
    return _public(creator)


@router.get("/{creator_id}/status")
async def status(creator_id: str):
    creator = await _require_creator(creator_id)
    return _public(creator)
