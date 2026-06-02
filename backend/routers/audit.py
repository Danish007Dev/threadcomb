"""Audit Report endpoints and orchestrator (Session 3).

Wires together:
  - 3 MongoDB aggregation pipelines
  - Gemini Pro synthesis
  - PDF generation → GCS upload
  - MongoDB storage
  - SSE notification
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from database.mongodb import get_db_singleton
from routers.auth import get_current_creator
from services.sse_manager import publish_sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("/generate/{creator_id}")
async def trigger_audit_generation(
    creator_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    Triggers Audit Report generation for a creator.
    Called automatically when ingestion job reaches QUEUED_FOR_EXTRACTION
    and all threads are extracted. Also callable manually.
    """
    if current_creator.get("creator_id") != creator_id:
        raise HTTPException(status_code=403)

    background_tasks.add_task(run_audit_generation, creator_id=creator_id)
    return {"status": "generating", "message": "Your audit report is being prepared."}


@router.get("/report/{creator_id}")
async def get_audit_report(
    creator_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Returns the latest audit report for a creator."""
    print(f"DEBUG: get_audit_report called for creator_id: {creator_id}")
    if current_creator.get("creator_id") != creator_id:
        print(f"DEBUG: 403 Forbidden. current_creator: {current_creator.get('creator_id')}")
        raise HTTPException(status_code=403)

    db = get_db_singleton()
    report = await db.audit_reports.find_one(
        {"creator_id": creator_id},
        sort=[("created_at", -1)]
    )
    if not report:
        print(f"DEBUG: 404 No audit report yet for {creator_id}")
        raise HTTPException(status_code=404, detail="No audit report yet")

    print(f"DEBUG: Found report: {report['_id']}")
    report["_id"] = str(report["_id"])
    return report


async def run_audit_generation(creator_id: str):
    """Full audit generation pipeline — runs in background."""
    from services.audit_pipelines import pipeline_revenue_leakage, pipeline_payment_reliability, pipeline_rate_gap
    from services.audit_generator import generate_audit_report
    from services.pdf_generator import generate_audit_pdf, upload_audit_pdf_to_gcs
    from models.audit import SynthesisContext

    db = get_db_singleton()

    try:
        creator = await db.creators.find_one({"creator_id": creator_id})
        if not creator:
            # Try by _id
            try:
                creator = await db.creators.find_one({"creator_id": creator_id})
            except Exception:
                pass
        if not creator:
            logger.error(f"Creator {creator_id} not found for audit generation")
            return

        # Run all 3 pipelines
        leakage = await pipeline_revenue_leakage(db, creator_id)
        payment = await pipeline_payment_reliability(db, creator_id)
        rate_gap = await pipeline_rate_gap(db, creator_id)

        # Get skills_map confirmed preferences
        prefs = await db.skills_map.find(
            {"creator_id": creator_id, "evidence.confidence": {"$gte": 0.7}}
        ).to_list(20)

        # Total extraction counts
        total_deals = await db.deals.count_documents({"creator_id": creator_id})
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
            total_deals_found=total_deals + total_hitl,
            total_deals_extracted=total_deals,
            total_confidence_below_threshold=total_hitl,
            confirmed_preferences=[{
                "name": p.get("name"), "value": p.get("preference", {}).get("value"),
                "confidence": p.get("evidence", {}).get("confidence")
            } for p in prefs],
        )

        # Gemini Pro synthesis
        report = await generate_audit_report(context)

        # Generate PDF (wrapped in to_thread since reportlab is synchronous)
        import asyncio
        pdf_bytes = await asyncio.to_thread(
            generate_audit_pdf,
            report,
            creator_handle=creator.get("handle", "Creator"),
            creator_niche=creator.get("niche", "creator")
        )
        pdf_url = await upload_audit_pdf_to_gcs(pdf_bytes, creator_id)

        # Store report in MongoDB
        report_doc = {
            "creator_id": creator_id,
            "findings": [f.model_dump() for f in report.findings],
            "executive_summary": report.executive_summary,
            "total_recoverable_value": report.total_recoverable_value,
            "total_recoverable_unknown": report.total_recoverable_unknown,
            "skills_map_summary": report.skills_map_summary,
            "data_quality_note": report.data_quality_note,
            "pdf_url": pdf_url,
            "created_at": datetime.now(timezone.utc),
            "data_classification": {
                "tier": "personal_identifiable",
                "deletion_policy": "on_request_30d",
                "export_eligible": True,
            }
        }
        await db.audit_reports.insert_one(report_doc)

        # Notify creator via SSE
        await publish_sse_event(creator_id, {
            "event": "audit_complete",
            "message": "Your Skills Audit is ready.",
            "pdf_url": pdf_url,
        })

        logger.info(f"Audit generation complete for creator {creator_id}")

    except Exception as e:
        logger.error(f"Audit generation error for creator {creator_id}: {e}", exc_info=True)
        await publish_sse_event(creator_id, {
            "event": "audit_error",
            "message": "Something went wrong generating your audit. Our team has been notified.",
        })
