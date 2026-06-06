# backend/routers/internal.py
"""
Internal endpoints called by Google Cloud Scheduler.
Protected by OIDC token verification.
Each endpoint runs a background operation across all active creators.

Cloud Scheduler sends a POST with an OIDC token in the Authorization header.
In production: verify the token. In development: accept requests with DEBUG=True.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from config import settings
from database.mongodb import get_db_singleton

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_scheduler_request(request: Request) -> bool:
    """
    Verifies the request came from Cloud Scheduler via OIDC token.
    In DEBUG mode: accepts all requests (for local testing).
    In production: verifies Authorization header contains a valid Google OIDC token.
    """
    from services.oidc_auth import verify_oidc_token
    from config import settings
    
    return verify_oidc_token(
        request,
        audience=settings.SCHEDULER_AUDIENCE,
        endpoint_name="internal_scheduler_endpoint"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1: Renew Gmail watches
# Cloud Scheduler: every 6 days at 9AM IST
# Gmail push notifications expire after 7 days — must renew before expiry.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/internal/renew-gmail-watches")
async def renew_gmail_watches(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Renews Gmail push notification watches for all active creators.
    Called by Cloud Scheduler every 6 days.
    Gmail watch expiry is 7 days — renew at 6 days to avoid any gap.
    """
    if not _verify_scheduler_request(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    background_tasks.add_task(_renew_all_gmail_watches)
    return {"status": "scheduled", "message": "Gmail watch renewal started for all active creators"}


async def _renew_all_gmail_watches():
    """Background task: renews Gmail watch for every creator approaching expiry."""
    from services.gmail_watch import register_gmail_watch
    from services.gmail_auth import get_gmail_credentials

    db = get_db_singleton()

    # Find creators whose watch expires within 24 hours OR has already expired
    expiry_threshold = datetime.utcnow() + timedelta(hours=24)

    creators = await db.creators.find({
        "gmail_connected": True,
        "$or": [
            {"gmail_watch.expiry": {"$lte": expiry_threshold}},
            {"gmail_watch.active": False},
            {"gmail_watch.expiry": {"$exists": False}},
        ]
    }).to_list(500)

    logger.info(f"Gmail watch renewal: {len(creators)} creators need renewal")

    renewed = 0
    failed = 0

    for creator in creators:
        creator_id = creator.get("creator_id", str(creator["_id"]))
        try:
            credentials = await get_gmail_credentials(creator_id)
            watch_data = await register_gmail_watch(credentials, creator_id)

            await db.creators.update_one(
                {"_id": creator["_id"]},
                {"$set": {
                    "gmail_watch.history_id": watch_data["history_id"],
                    "gmail_watch.expiry": watch_data["expiry"],
                    "gmail_watch.active": True,
                    "gmail_watch.topic_name": watch_data["topic_name"],
                    "updated_at": datetime.utcnow(),
                }}
            )
            renewed += 1
            logger.info(f"Gmail watch renewed for creator {creator_id}. Expires: {watch_data['expiry']}")

        except Exception as e:
            failed += 1
            logger.error(f"Gmail watch renewal failed for creator {creator_id}: {e}")
            # Mark watch as inactive so it's retried next run
            await db.creators.update_one(
                {"_id": creator["_id"]},
                {"$set": {"gmail_watch.active": False, "updated_at": datetime.utcnow()}}
            )

    logger.info(f"Gmail watch renewal complete. Renewed: {renewed}, Failed: {failed}")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: Run pattern synthesis
# Cloud Scheduler: weekly, Sunday 2AM IST
# Re-runs Skills Map synthesis for creators with new data since last synthesis.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/internal/run-pattern-synthesis")
async def run_pattern_synthesis(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Runs Skills Map pattern synthesis for all creators with new deal data.
    Called by Cloud Scheduler weekly (Sunday 2AM IST).
    Synthesis re-runs aggregation pipelines and updates preference nodes.
    """
    if not _verify_scheduler_request(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    background_tasks.add_task(_run_synthesis_for_all_creators)
    return {"status": "scheduled", "message": "Pattern synthesis started for qualifying creators"}


async def _run_synthesis_for_all_creators():
    """
    Background task: re-runs Skills Map synthesis for creators who have
    received new deals since their last synthesis run.
    """
    from services.audit_pipelines import (
        pipeline_revenue_leakage,
        pipeline_payment_reliability,
        pipeline_rate_gap,
    )
    from services.audit_generator import generate_audit_report
    from models.audit import SynthesisContext

    db = get_db_singleton()

    # Find creators who:
    # 1. Have connected Gmail (have data to synthesise)
    # 2. Either have never been synthesised OR haven't been synthesised in 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    creators = await db.creators.find({
        "gmail_connected": True,
        "$or": [
            {"last_synthesis_at": {"$exists": False}},
            {"last_synthesis_at": {"$lt": seven_days_ago}},
        ]
    }).to_list(200)

    logger.info(f"Pattern synthesis: {len(creators)} creators to process")

    for creator in creators:
        creator_id = creator.get("creator_id", str(creator["_id"]))
        try:
            # Check if creator actually has deals to synthesise
            deal_count = await db.deals.count_documents({"creator_id": creator_id})
            if deal_count == 0:
                logger.info(f"Skipping synthesis for creator {creator_id} — no deals yet")
                continue

            logger.info(f"Running synthesis for creator {creator_id} ({deal_count} deals)")

            # Run the 3 aggregation pipelines
            leakage = await pipeline_revenue_leakage(db, creator_id)
            payment = await pipeline_payment_reliability(db, creator_id)
            rate_gap = await pipeline_rate_gap(db, creator_id)

            # Fetch confirmed preferences
            prefs = await db.skills_map.find(
                {"creator_id": creator_id, "evidence.confidence": {"$gte": 0.7}}
            ).to_list(20)

            total_hitl = await db.agent_actions.count_documents({
                "creator_id": creator_id,
                "action_type": "hitl_queued"
            })

            context = SynthesisContext(
                creator_id=creator_id,
                creator_niche=creator.get("niche", ""),
                creator_follower_tier=creator.get("follower_tier", ""),
                creator_handle=creator.get("handle"),
                unanswered_deal_count=leakage.get("unanswered_deals", 0),
                unanswered_value_typical=leakage.get("estimated_value_typical", 0),
                unanswered_value_min=leakage.get("estimated_value_min", 0),
                unanswered_value_max=leakage.get("estimated_value_max", 0),
                has_financial_estimates=leakage.get("has_estimates", False),
                payment_reliability_data=payment,
                rate_gap_data=rate_gap,
                total_deals_found=deal_count + total_hitl,
                total_deals_extracted=deal_count,
                total_confidence_below_threshold=total_hitl,
                confirmed_preferences=[{
                    "name": p.get("name"),
                    "value": p.get("preference", {}).get("value"),
                    "confidence": p.get("evidence", {}).get("confidence"),
                } for p in prefs],
            )

            # Generate updated Audit Report
            report = await generate_audit_report(context)

            # Generate and store PDF
            from services.pdf_generator import generate_audit_pdf, upload_audit_pdf_to_gcs
            pdf_bytes = await asyncio.to_thread(
                generate_audit_pdf,
                report,
                creator_handle=creator.get("handle", "Creator"),
                creator_niche=creator.get("niche", "creator"),
            )
            pdf_url = await upload_audit_pdf_to_gcs(pdf_bytes, creator_id)

            # Store updated report
            report_doc = {
                "creator_id": creator_id,
                "findings": [f.model_dump() for f in report.findings],
                "executive_summary": report.executive_summary,
                "total_recoverable_value": report.total_recoverable_value,
                "total_recoverable_unknown": report.total_recoverable_unknown,
                "skills_map_summary": report.skills_map_summary,
                "data_quality_note": report.data_quality_note,
                "pdf_url": pdf_url,
                "synthesis_trigger": "scheduled_weekly",
                "created_at": datetime.utcnow(),
                "data_classification": {
                    "tier": "personal_identifiable",
                    "deletion_policy": "on_request_30d",
                    "export_eligible": True,
                }
            }
            await db.audit_reports.insert_one(report_doc)

            # Update creator's last_synthesis_at
            await db.creators.update_one(
                {"_id": creator["_id"]},
                {"$set": {
                    "last_synthesis_at": datetime.utcnow(),
                    "skills_map_version": creator.get("skills_map_version", 0) + 1,
                    "updated_at": datetime.utcnow(),
                }}
            )

            logger.info(f"Synthesis complete for creator {creator_id}. PDF: {pdf_url}")

        except Exception as e:
            logger.error(f"Synthesis error for creator {creator_id}: {e}", exc_info=True)
            # Continue with next creator — one failure should not stop the batch

    logger.info("Pattern synthesis run complete.")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3: Check overdue invoices
# Cloud Scheduler: daily at 6:30AM IST (0 1 * * * UTC)
# Runs Revenue Guardian for every creator with overdue invoices.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/internal/check-overdue-invoices")
async def check_overdue_invoices(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Runs Revenue Guardian for all creators with overdue invoices.
    Called by Cloud Scheduler daily at 6:30AM IST.
    Also updates days_overdue field for all pending invoices before running.
    """
    if not _verify_scheduler_request(request):
        raise HTTPException(status_code=403, detail="Unauthorized")

    background_tasks.add_task(_check_all_overdue_invoices)
    return {"status": "scheduled", "message": "Overdue invoice check started for all creators"}


async def _check_all_overdue_invoices():
    """
    Background task:
    Step 1 — Updates days_overdue for all pending invoices (MongoDB update, not Python loop)
    Step 2 — Finds creators with at least 1 overdue invoice
    Step 3 — Runs Revenue Guardian for each
    """
    from services.revenue_guardian import run_revenue_guardian

    db = get_db_singleton()
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Step 1: Update days_overdue for all pending/overdue invoices
    # This is a bulk MongoDB operation — not a Python loop
    # Use aggregation pipeline update to compute days_overdue from due_date
    await db.invoices.update_many(
        {
            "status": {"$in": ["pending", "sent", "overdue"]},
            "due_date": {"$exists": True, "$lt": today},
        },
        [
            {
                "$set": {
                    "days_overdue": {
                        "$toInt": {
                            "$divide": [
                                {"$subtract": [today, "$due_date"]},
                                1000 * 60 * 60 * 24  # milliseconds per day
                            ]
                        }
                    },
                    "status": "overdue",
                    "updated_at": today,
                }
            }
        ]
    )

    # Step 2: Find distinct creator_ids with overdue invoices
    overdue_creator_ids = await db.invoices.distinct(
        "creator_id",
        {
            "status": {"$in": ["overdue", "pending"]},
            "days_overdue": {"$gt": 0},
        }
    )

    logger.info(f"Overdue invoice check: {len(overdue_creator_ids)} creators with overdue invoices")

    # Step 3: Run Revenue Guardian for each creator
    # Run sequentially to avoid overwhelming Gemini API rate limits
    guardian_ran = 0
    guardian_skipped = 0

    for creator_id in overdue_creator_ids:
        try:
            await run_revenue_guardian(creator_id=str(creator_id))
            guardian_ran += 1
            # Small delay between creators to respect Gemini rate limits
            await asyncio.sleep(2)
        except Exception as e:
            guardian_skipped += 1
            logger.error(f"Revenue Guardian error for creator {creator_id}: {e}")

    logger.info(f"Overdue invoice check complete. Guardian ran: {guardian_ran}, Skipped: {guardian_skipped}")


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH endpoint for Cloud Scheduler verification
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/internal/health")
async def internal_health():
    """Quick health check for internal scheduler verification."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
