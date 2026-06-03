from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timedelta
import logging

from routers.auth import get_current_creator
from database.mongodb import get_db_singleton
from services.revenue_guardian import run_revenue_guardian
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/guardian/run")
async def trigger_guardian(
    background_tasks: BackgroundTasks,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Manually triggers Revenue Guardian. Also called by Cloud Scheduler."""
    creator_id = current_creator["creator_id"]
    background_tasks.add_task(run_revenue_guardian, creator_id=creator_id)
    return {"status": "running", "message": "Checking your invoices..."}


@router.get("/guardian/pending")
async def get_pending_followups(
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Returns the latest batch of pending follow-up drafts for creator review."""
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()

    batch = await db.invoice_followups.find_one(
        {"creator_id": creator_id},
        sort=[("run_date", -1)]
    )
    if not batch:
        return {"drafts": [], "total_overdue": 0}

    batch["_id"] = str(batch["_id"])
    return batch


@router.post("/guardian/approve-batch")
async def approve_followup_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    current_creator=Depends(get_current_creator),
):
    """
    Creator approves some or all follow-up drafts.
    Body: {approved_invoice_ids: ["id1", "id2"], skipped_invoice_ids: ["id3"]}
    Sends approved follow-ups and updates invoice records.
    """
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()
    body = await request.json()

    approved_ids = body.get("approved_invoice_ids", [])
    skipped_ids = body.get("skipped_invoice_ids", [])

    if not approved_ids and not skipped_ids:
        raise HTTPException(status_code=400, detail="No invoice IDs provided")

    # Fetch the latest batch to get draft texts
    batch = await db.invoice_followups.find_one(
        {"creator_id": creator_id},
        sort=[("run_date", -1)]
    )
    if not batch:
        raise HTTPException(status_code=404, detail="No pending follow-ups found")

    drafts_map = {d["invoice_id"]: d for d in batch.get("drafts", [])}

    sent_count = 0
    for invoice_id in approved_ids:
        draft = drafts_map.get(invoice_id)
        if not draft:
            continue
        background_tasks.add_task(
            send_invoice_followup,
            creator_id=creator_id,
            invoice_id=invoice_id,
            draft_text=draft["draft_text"],
            batch_id=str(batch["_id"]),
        )
        sent_count += 1

    # Mark skipped
    for invoice_id in skipped_ids:
        await db.invoice_followups.update_one(
            {"_id": batch["_id"], "drafts.invoice_id": invoice_id},
            {"$set": {"drafts.$.creator_action": "skipped"}}
        )

    return {
        "status": "ok",
        "sent": sent_count,
        "skipped": len(skipped_ids),
    }


@router.post("/guardian/approve-single/{invoice_id}")
async def approve_single_followup(
    invoice_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_creator=Depends(get_current_creator),
):
    """Approves and sends a single follow-up."""
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()
    body = await request.json()
    final_text = body.get("final_text")

    if not final_text:
        # Get the draft from the latest batch
        batch = await db.invoice_followups.find_one(
            {"creator_id": creator_id, "drafts.invoice_id": invoice_id},
            sort=[("run_date", -1)]
        )
        if not batch:
            raise HTTPException(status_code=404, detail="Draft not found")
        draft = next((d for d in batch.get("drafts", []) if d["invoice_id"] == invoice_id), None)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found for this invoice")
        final_text = draft["draft_text"]

    background_tasks.add_task(
        send_invoice_followup,
        creator_id=creator_id,
        invoice_id=invoice_id,
        draft_text=final_text,
        batch_id=None,
    )

    return {"status": "sending", "invoice_id": invoice_id}


async def send_invoice_followup(
    creator_id: str,
    invoice_id: str,
    draft_text: str,
    batch_id: str = None,
):
    """
    Background function: sends follow-up email and updates invoice + brand records.
    ACTION_POLICY: send_email ALWAYS requires creator approval.
    This is called ONLY from /guardian/approve-batch or /guardian/approve-single.
    """
    from services.gmail_sender import send_gmail_reply
    from services.sse_manager import publish_sse_event
    from database.mongodb import get_db_singleton
    from services.calendar_service import create_followup_event

    db = get_db_singleton()

    try:
        invoice = await db.invoices.find_one({"_id": ObjectId(invoice_id)})
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found")
            return

        # Get the Gmail thread ID from the associated deal
        deal = await db.deals.find_one({"_id": ObjectId(str(invoice.get("deal_id", "")))})
        thread_id = deal.get("raw_signals", {}).get("gmail_thread_id", "") if deal else ""

        if thread_id:
            sent_id = await send_gmail_reply(
                creator_id=creator_id,
                thread_id=thread_id,
                body_text=draft_text,
            )
        else:
            # No thread ID — log and skip send (can't send without thread context)
            logger.warning(f"No Gmail thread ID for invoice {invoice_id}. Follow-up logged but not sent.")
            sent_id = None

        # Update invoice record
        await db.invoices.update_one(
            {"_id": ObjectId(invoice_id)},
            {
                "$set": {
                    "status": "overdue" if invoice.get("days_overdue", 0) > 0 else "pending",
                    "follow_ups.last_sent_at": datetime.utcnow(),
                    "follow_ups.next_due_at": datetime.utcnow() + timedelta(days=7),
                    "updated_at": datetime.utcnow(),
                },
                "$inc": {"follow_ups.count": 1},
                "$push": {
                    "follow_ups.tones_used": invoice.get("recommended_tone", "gentle")
                }
            }
        )

        # Update batch record
        if batch_id:
            await db.invoice_followups.update_one(
                {"_id": ObjectId(batch_id), "drafts.invoice_id": invoice_id},
                {
                    "$set": {
                        "drafts.$.creator_action": "approved",
                        "drafts.$.sent_at": datetime.utcnow(),
                    },
                    "$inc": {"total_sent": 1}
                }
            )

        # Update brand payment intelligence — this is Loop 2 (per-outcome learning)
        brand_id = invoice.get("brand_id")
        if brand_id:
            await db.brands.update_one(
                {"_id": ObjectId(str(brand_id))},
                {
                    "$inc": {"payment_intelligence.follow_up_required_count": 1},
                    "$set": {"updated_at": datetime.utcnow()},
                }
            )

        # Create Calendar reminder: check payment in 7 days
        brand_doc = await db.brands.find_one({"_id": ObjectId(str(brand_id))}) if brand_id else None
        brand_name = brand_doc.get("name", "Brand") if brand_doc else "Brand"
        amount = invoice.get("amount_inr", 0)

        try:
            await create_followup_event(
                creator_id=creator_id,
                title=f"Check payment: {brand_name} — ₹{amount:,.0f}",
                date=datetime.utcnow() + timedelta(days=7),
                description=f"Follow-up sent on {datetime.utcnow().strftime('%b %d')}. Check if payment received.",
            )
        except Exception as e:
            logger.warning(f"Calendar event failed for invoice follow-up (non-critical): {e}")

        # Notify creator
        await publish_sse_event(creator_id, {
            "event": "followup_sent",
            "invoice_id": invoice_id,
            "brand_name": brand_name,
            "message": f"Follow-up sent to {brand_name}. Reminder set for 7 days.",
        })

        # Log agent action
        from models.common import AgentActionType, ActionResult, DataClassificationTier
        from services.mongodb_writer import write_with_classification
        await write_with_classification(
            db.agent_actions,
            {
                "creator_id": creator_id,
                "agent": "revenue_guardian",
                "action_type": AgentActionType.EMAIL_SENT.value if hasattr(AgentActionType, 'EMAIL_SENT') else "email_sent",
                "execution": {"model_used": "gemini-2.5-flash"},
                "decision": {
                    "invoice_id": invoice_id,
                    "brand_name": brand_name,
                    "amount_inr": amount,
                },
                "outcome": {
                    "result": ActionResult.SUCCESS.value if hasattr(ActionResult, 'SUCCESS') else "success",
                    "gmail_message_id": sent_id,
                },
            },
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

    except Exception as e:
        logger.error(f"Send invoice follow-up error for {invoice_id}: {e}", exc_info=True)


@router.post("/guardian/weekly-digest/{creator_id}")
async def weekly_digest(
    creator_id: str,
    request: Request,
):
    """
    Called by Cloud Scheduler every Monday at 8AM IST.
    Also callable manually for testing.
    Generates a weekly revenue summary for the creator.
    """
    # Verify scheduler secret to prevent unauthorized calls
    scheduler_secret = request.headers.get("X-Scheduler-Secret", "")
    if hasattr(settings, "WORKER_SECRET") and scheduler_secret != getattr(settings, "WORKER_SECRET", "") and not getattr(settings, "DEBUG", False):
        raise HTTPException(status_code=403)

    db = get_db_singleton()
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Paid this week
    paid_pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": "paid",
            "paid_date": {"$gte": week_ago}
        }},
        {"$group": {
            "_id": None,
            "total_paid": {"$sum": "$amount_inr"},
            "count": {"$sum": 1}
        }}
    ]
    paid = await db.invoices.aggregate(paid_pipeline).to_list(1)
    paid_this_week = paid[0] if paid else {"total_paid": 0, "count": 0}

    # Still outstanding
    outstanding_pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": {"$in": ["pending", "overdue"]},
        }},
        {"$group": {
            "_id": None,
            "total_outstanding": {"$sum": "$amount_inr"},
            "overdue_count": {"$sum": {"$cond": [{"$eq": ["$status", "overdue"]}, 1, 0]}},
        }}
    ]
    outstanding = await db.invoices.aggregate(outstanding_pipeline).to_list(1)
    outstanding_data = outstanding[0] if outstanding else {"total_outstanding": 0, "overdue_count": 0}

    # Follow-ups sent this week
    followups_sent = await db.agent_actions.count_documents({
        "creator_id": creator_id,
        "agent": "revenue_guardian",
        "action_type": "email_sent",
        "executed_at": {"$gte": week_ago}
    })

    # Publish as SSE event
    from services.sse_manager import publish_sse_event
    await publish_sse_event(creator_id, {
        "event": "weekly_digest",
        "paid_this_week_inr": paid_this_week.get("total_paid", 0),
        "paid_count": paid_this_week.get("count", 0),
        "outstanding_inr": outstanding_data.get("total_outstanding", 0),
        "overdue_count": outstanding_data.get("overdue_count", 0),
        "followups_sent": followups_sent,
        "message": "Your weekly revenue summary is ready.",
    })

    return {"status": "sent", "creator_id": creator_id}


@router.post("/guardian/weekly-digest/all")
async def weekly_digest_all(
    request: Request,
):
    """
    Called by Cloud Scheduler.
    Iterates over all active creators and calls weekly digest for each.
    """
    scheduler_secret = request.headers.get("X-Scheduler-Secret", "")
    if hasattr(settings, "WORKER_SECRET") and scheduler_secret != getattr(settings, "WORKER_SECRET", "") and not getattr(settings, "DEBUG", False):
        raise HTTPException(status_code=403)

    db = get_db_singleton()
    
    active_creators = await db.creators.find({
        "gmail_connected": True, 
        "subscription.status": "active"
    }).to_list(1000)
    
    for creator in active_creators:
        try:
            creator_id = creator.get("creator_id", str(creator["_id"]))
            await weekly_digest(creator_id, request)
        except Exception as e:
            logger.error(f"Failed to generate weekly digest for {creator_id}: {e}")
            
    return {"status": "processed", "count": len(active_creators)}
