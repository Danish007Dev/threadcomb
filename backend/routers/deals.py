# backend/routers/deals.py

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timedelta
import asyncio
import logging

from routers.auth import get_current_creator
from database.mongodb import get_db_singleton

router = APIRouter(prefix="/deals", tags=["deals"])
logger = logging.getLogger(__name__)


@router.get("/inbound")
async def get_inbound_deals(
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    Returns all inbound deals for the creator that have a pending draft or need attention.
    Sorted by: unanswered first, then by date descending.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    deals = await db.deals.find(
        {
            "creator_id": creator_id,
            "status": {"$in": ["unanswered", "negotiating"]},
        },
        sort=[("created_at", -1)],
        limit=50
    ).to_list(50)

    # Enrich with brand data
    enriched = []
    for deal in deals:
        deal["_id"] = str(deal["_id"])
        if deal.get("brand_id"):
            try:
                brand = await db.brands.find_one({"_id": ObjectId(deal["brand_id"])})
            except Exception:
                brand = None
            if brand:
                deal["brand"] = {
                    "name": brand.get("name"),
                    "domain": brand.get("domain"),
                    "payment_reliability": brand.get("payment_intelligence", {}).get("payment_reliability", 0.5),
                    "avg_payment_days": brand.get("payment_intelligence", {}).get("avg_payment_days"),
                }
        # Check if a draft exists for this deal
        draft = await db.deal_drafts.find_one(
            {"deal_id": deal["_id"], "creator_action": None},
            sort=[("generated_at", -1)]
        )
        deal["has_pending_draft"] = draft is not None
        enriched.append(deal)

    return enriched


@router.post("/generate-draft/{deal_id}")
async def generate_deal_draft(
    deal_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_creator=Depends(get_current_creator),
):
    """
    Triggers Deal Chief pipeline for a specific deal.
    Returns immediately — draft pushed via SSE when ready.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    deal = await db.deals.find_one(
        {"_id": ObjectId(deal_id), "creator_id": creator_id}
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    background_tasks.add_task(
        run_deal_chief_for_deal,
        deal_id=deal_id,
        creator_id=creator_id,
    )

    return {"status": "generating", "message": "Draft will be ready in a few seconds."}


@router.get("/draft/{deal_id}")
async def get_deal_draft(
    deal_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Returns the latest pending draft for a deal."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    draft = await db.deal_drafts.find_one(
        {"deal_id": deal_id, "creator_id": creator_id},
        sort=[("generated_at", -1)]
    )
    if not draft:
        raise HTTPException(status_code=404, detail="No draft found")

    draft["_id"] = str(draft["_id"])
    return draft


@router.post("/approve/{deal_id}")
async def approve_deal_draft(
    deal_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    Creator approves (possibly with edits) and sends the reply.
    ACTION_POLICY: send_email ALWAYS requires creator approval. This endpoint IS that approval.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    body = await request.json()
    final_text = body.get("final_text")  # Creator may have edited the draft
    action = body.get("action", "approved")  # "approved" | "edited"
    follow_up_days = body.get("follow_up_days", 3)

    if not final_text:
        raise HTTPException(status_code=400, detail="final_text is required")

    # Fetch the deal
    deal = await db.deals.find_one(
        {"_id": ObjectId(deal_id), "creator_id": creator_id}
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Fetch the draft for metadata
    draft = await db.deal_drafts.find_one(
        {"deal_id": deal_id, "creator_id": creator_id, "creator_action": None},
        sort=[("generated_at", -1)]
    )

    try:
        # ── Send the email ────────────────────────────────────────────────────
        from services.gmail_sender import send_gmail_reply
        sent_message_id = await send_gmail_reply(
            creator_id=creator_id,
            thread_id=deal["raw_signals"]["gmail_thread_id"],
            body_text=final_text,
        )

        # ── Create Calendar follow-up reminder ────────────────────────────────
        calendar_event_id = None
        try:
            from services.calendar_service import create_followup_event
            follow_up_date = datetime.utcnow() + timedelta(days=follow_up_days)
            brand_name = deal.get("brand_name") or (draft.get("brand_name", "Brand") if draft else "Brand")
            calendar_event_id = await create_followup_event(
                creator_id=creator_id,
                title=f"Follow up: {brand_name} deal",
                date=follow_up_date,
                description=f"Check for response on brand deal. ThreadComb draft was approved on {datetime.utcnow().strftime('%b %d')}.",
            )
        except Exception as e:
            logger.warning(f"Calendar event creation failed (non-critical): {e}")

        # ── Update deal status ────────────────────────────────────────────────
        await db.deals.update_one(
            {"_id": ObjectId(deal_id)},
            {"$set": {
                "status": "negotiating",
                "updated_at": datetime.utcnow(),
            }}
        )

        # ── Update draft record ───────────────────────────────────────────────
        if draft:
            await db.deal_drafts.update_one(
                {"_id": draft["_id"]},
                {"$set": {
                    "creator_action": action,
                    "final_text": final_text,
                    "sent_at": datetime.utcnow(),
                    "calendar_event_id": calendar_event_id,
                }}
            )

        # ── Log agent action ──────────────────────────────────────────────────
        from models.common import AgentActionType, ActionResult, DataClassificationTier
        from services.mongodb_writer import write_with_classification
        await write_with_classification(
            db.agent_actions,
            {
                "creator_id": creator_id,
                "agent": "deal_chief",
                "action_type": AgentActionType.EMAIL_SENT.value,
                "execution": {
                    "model_used": draft.get("model_used") if draft else "unknown",
                    "voice_compliance_score": draft.get("voice_compliance_score") if draft else None,
                },
                "decision": {
                    "creator_action": action,
                    "draft_was_edited": action == "edited",
                    "brand_name": deal.get("brand_name"),
                    "flags_count": len(draft.get("flags", [])) if draft else 0,
                },
                "outcome": {
                    "result": ActionResult.SUCCESS.value,
                    "gmail_message_id": sent_message_id,
                    "calendar_event_id": calendar_event_id,
                },
            },
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

        return {
            "status": "sent",
            "message": "Reply sent successfully.",
            "calendar_event_created": calendar_event_id is not None,
            "follow_up_date": (datetime.utcnow() + timedelta(days=follow_up_days)).isoformat(),
        }

    except Exception as e:
        logger.error(f"Deal approval/send error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")


@router.post("/reject/{deal_id}")
async def reject_deal_draft(
    deal_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Creator rejects the draft — marks deal as reviewed, no email sent."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    body = await request.json()
    reason = body.get("reason", "")

    # Bug 2 fix: update_one doesn't support sort — use find_one_and_update instead
    await db.deal_drafts.find_one_and_update(
        {"deal_id": deal_id, "creator_id": creator_id, "creator_action": None},
        {"$set": {"creator_action": "rejected", "rejection_reason": reason}},
        sort=[("generated_at", -1)]
    )
    await db.deals.update_one(
        {"_id": ObjectId(deal_id)},
        {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}}
    )
    return {"status": "ok", "message": "Deal marked as rejected."}


# ── Background orchestrator ───────────────────────────────────────────────────

async def run_deal_chief_for_deal(deal_id: str, creator_id: str):
    """
    Background function: fetches deal context and runs Deal Chief pipeline.
    Pushes DraftResult to creator via SSE when complete.
    Stores DraftResult in deal_drafts collection.
    """
    from services.deal_chief import run_deal_chief_pipeline
    from services.sse_manager import publish_sse_event
    from models.deal import DealExtraction
    from services.mongodb_writer import write_with_classification
    from models.common import DataClassificationTier

    db = get_db_singleton()

    try:
        deal = await db.deals.find_one({"_id": ObjectId(deal_id)})
        if not deal:
            return

        # Look up brand doc for name and category (not stored in deal doc directly)
        brand_name = None
        brand_category = None
        brand_domain = None
        if deal.get("brand_id"):
            try:
                brand_doc = await db.brands.find_one({"_id": ObjectId(deal["brand_id"])})
                if brand_doc:
                    brand_name = brand_doc.get("name")
                    brand_category = brand_doc.get("category")
                    brand_domain = brand_doc.get("domain")
            except Exception:
                pass

        # Fallback: derive brand_domain from sender email
        sender_email = deal.get("raw_signals", {}).get("brand_contact_email", "")
        if not brand_domain and sender_email:
            brand_domain = sender_email.split("@")[-1]

        # Reconstruct minimal DealExtraction from stored deal document
        extraction = DealExtraction(
            brand_name=brand_name,
            brand_domain=brand_domain,
            brand_category=brand_category,
            deal_type=deal.get("deal_type"),
            amount_ambiguity_flag=deal.get("financials", {}).get("amount_ambiguity_flag", False),
            amount_raw_text=deal.get("financials", {}).get("amount_raw_text"),
            amount_typical=deal.get("financials", {}).get("amount_inr"),
            amount_min=deal.get("financials", {}).get("amount_min"),
            amount_max=deal.get("financials", {}).get("amount_max"),
            currency=deal.get("financials", {}).get("currency", "INR"),
            deliverables=deal.get("raw_signals", {}).get("deliverables", []),
            exclusivity_mentioned=deal.get("raw_signals", {}).get("exclusivity_mentioned", False),
            exclusivity_duration_days=deal.get("raw_signals", {}).get("exclusivity_duration_days"),
            # payment_terms is in financials, not raw_signals
            payment_terms_mentioned=deal.get("financials", {}).get("payment_terms"),
            is_agency_contact=deal.get("raw_signals", {}).get("is_agency_contact", False),
            gmail_thread_id=deal.get("raw_signals", {}).get("gmail_thread_id", ""),
            sender_email=sender_email,
            extraction_confidence=deal.get("extraction_confidence", 0.7),
        )

        # Note: sanitised thread text is not stored (Principle 3).
        # For the Deal Chief pipeline, we use a short summary from the extraction
        # rather than the full thread text. The draft quality is slightly lower
        # than if we had the full thread, but privacy compliance is maintained.
        thread_summary = f"Brand deal email from {extraction.brand_domain}. " \
                        f"Deliverables: {', '.join(extraction.deliverables)}. " \
                        f"{'Amount: ₹' + str(extraction.amount_typical) if extraction.amount_typical else 'Amount: not stated'}."

        # Subject is not stored in the deal doc — use brand name as fallback
        deal_subject = f"Brand deal from {brand_name or brand_domain or 'unknown'}"

        draft_result = await run_deal_chief_pipeline(
            db=db,
            creator_id=creator_id,
            thread_id=deal.get("raw_signals", {}).get("gmail_thread_id", deal_id),
            sanitised_thread_text=thread_summary,
            sender_email=extraction.sender_email or "",
            subject=deal_subject,
            extraction=extraction,
        )

        # Set deal_id on draft result
        draft_result.deal_id = deal_id

        # Store draft in deal_drafts collection
        draft_doc = draft_result.model_dump()
        draft_doc["flags"] = [f.model_dump() for f in draft_result.flags]
        await write_with_classification(
            db.deal_drafts,
            draft_doc,
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

        # Push to creator via SSE
        await publish_sse_event(creator_id, {
            "event": "draft_ready",
            "deal_id": deal_id,
            "brand_name": draft_result.brand_name,
            "voice_compliance_score": draft_result.voice_compliance_score,
            "flags_count": len(draft_result.flags),
            "has_high_severity_flags": draft_result.has_high_severity_flags,
            "latency_ms": draft_result.generation_latency_ms,
            "message": f"Reply draft ready for {draft_result.brand_name or 'this brand'}.",
        })

    except Exception as e:
        logger.error(f"Deal Chief pipeline error for deal {deal_id}: {e}", exc_info=True)
        from services.sse_manager import publish_sse_event
        await publish_sse_event(creator_id, {
            "event": "draft_error",
            "deal_id": deal_id,
            "message": "Could not generate draft. Please compose manually.",
        })
