# THREADCOMB — SESSION 5 PROMPT
# Revenue Guardian + Google ADK Orchestrator + Complete Dashboard + Hackathon Prep
# Next.js 15 + React 19 App Router, FastAPI, MongoDB Atlas, Google ADK
# Paste this entire document to Copilot Agent as context. Work section by section.

---

## IDENTITY ANCHOR

**Product:** ThreadComb — AI-powered creator operations platform.
**Stack:** Next.js 15 + React 19 (App Router, TypeScript) + FastAPI (Python 3.11, Pydantic v2, motor) + MongoDB Atlas M0 + Google Cloud ADK + Gemini API.

**What exists from Sessions 1–4:**
- MongoDB: all collections live including deal_drafts. Atlas Vector Search READY (768d cosine).
- Session 1: Auth, onboarding, MongoDB schema, ACTION_POLICY, write_with_classification.
- Session 2A: Corpus ingestion pipeline (niche_graph seeded).
- Session 2B: Gmail ingestion pipeline (fetch → sanitise → gate → Cloud Tasks queue).
- Session 3: DNA Reader extraction worker, Audit Report generation, First Signal module.
- Session 4: Deal Chief 8-step pipeline, voice compliance evaluator (Call B), deal approval → Gmail send → Calendar event. All 12 exit criteria passed including real Gmail send confirmed in Sent folder and two independent Gemini API calls confirmed in logs.
- Frontend: Dashboard (4 states), Audit page, Deals page with ShadowDraftModal.

**Session 5 builds:**
1. Revenue Guardian agent — overdue invoice detection, urgency scoring in MongoDB, tone-calibrated follow-up drafts, batch approval UI
2. Google ADK Master Orchestrator — natural language routing to all 3 agents via A2A
3. Complete Dashboard — deal pipeline, invoice tracker, activity feed, weekly digest widget
4. HITL Views 1 and 4 — extraction review queue and agent action audit
5. Data export (Skills Map JSON) and data deletion endpoint (DPDP compliance)
6. Hackathon demo data preparation and submission checklist

**Does NOT build:** Fan Management Agent (Phase 2), LangGraph migration (Phase 2), Arize Phoenix (Phase 2), Fivetran (Phase 2).

---

## PART 1 — REVENUE GUARDIAN AGENT

### The core design principle for this agent:
The `urgency_score` and `recommended_tone` are computed inside MongoDB aggregation pipelines — not in Python, not by Gemini. The agent reads data, MongoDB computes the ranking and tone recommendation, Gemini writes the follow-up text. This is the same principle as the Audit Report: AI narrates, MongoDB calculates.

### 1A — New Pydantic models

Build in `backend/models/invoice.py`:

```python
# backend/models/invoice.py

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class InvoiceFollowUpDraft(BaseModel):
    """A single follow-up draft for one overdue invoice."""
    invoice_id: str
    deal_id: Optional[str] = None
    creator_id: str
    brand_name: Optional[str] = None
    brand_domain: Optional[str] = None
    amount_inr: Optional[float] = None
    days_overdue: int
    urgency_score: float
    recommended_tone: Literal["gentle", "firm", "final_notice"]
    follow_up_count: int                     # how many previous follow-ups have been sent
    draft_text: str
    voice_compliance_score: float
    model_used: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    # Creator action
    creator_action: Optional[Literal["approved", "skipped"]] = None
    sent_at: Optional[datetime] = None
    data_classification: dict = Field(default_factory=lambda: {
        "tier": "personal_identifiable",
        "deletion_policy": "on_request_30d",
        "export_eligible": True,
    })


class BatchFollowUpResult(BaseModel):
    """Complete output of one Revenue Guardian run."""
    creator_id: str
    run_date: datetime = Field(default_factory=datetime.utcnow)
    total_overdue: int
    total_drafted: int
    total_sent: int
    total_skipped: int
    total_recovered_inr: float              # filled as invoices get paid
    drafts: List[InvoiceFollowUpDraft] = []
```

### 1B — The urgency aggregation pipeline — runs IN MongoDB

Build in `backend/services/revenue_guardian.py`:

```python
# backend/services/revenue_guardian.py

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import List
from bson import ObjectId
from google.genai import types

from backend.models.invoice import InvoiceFollowUpDraft, BatchFollowUpResult
from backend.models.common import DataClassificationTier, AgentActionType, ActionResult
from backend.services.mongodb_writer import write_with_classification

logger = logging.getLogger(__name__)

FOLLOWUP_MODEL = "gemini-2.5-flash"

# Tone-specific system prompts — each instilled with a different energy level
TONE_PROMPTS = {
    "gentle": """
You are writing a gentle payment reminder on behalf of a content creator in India.
Tone: Warm, assumes the delay is an oversight, not intentional. No pressure. Friendly.
Length: 60–90 words maximum.
Do NOT: threaten, express frustration, mention "final notice", or use formal legal language.
Do: Assume good faith. Mention the specific amount and invoice. Offer to resend the invoice.
""",
    "firm": """
You are writing a firm payment follow-up on behalf of a content creator in India.
Tone: Professional, direct, clear expectation. Polite but unambiguous.
Length: 80–120 words.
Do NOT: be aggressive, apologize for following up, or say "I hope this email finds you well."
Do: State the exact amount, days overdue, and a specific payment deadline (7 days from now).
Mention that you can resend the invoice if needed.
""",
    "final_notice": """
You are writing a final payment notice on behalf of a content creator in India.
Tone: Formal, serious, clear consequences. Not aggressive but unmistakably final.
Length: 100–150 words.
Do NOT: be rude, threaten legal action (unless instructed), or use emotional language.
Do: State this is the final notice before escalation. State exact amount, exact days overdue,
and a 5-day deadline. Mention that next steps will follow if payment is not received.
Reference the original contract or agreement if deliverables were completed.
"""
}

VOICE_GUARDIAN_SYSTEM = """
You are writing on behalf of a content creator. Match their voice profile exactly.
The tone instruction above sets the ENERGY LEVEL of the message.
The voice profile sets HOW that energy is expressed through their writing style.
A casual creator sending a final notice still sounds like themselves — just more serious than usual.
Return only the email body text. No subject line. No metadata.
"""


async def run_urgency_aggregation(db, creator_id: str) -> List[dict]:
    """
    Runs the urgency scoring aggregation entirely in MongoDB.
    Returns invoices ranked by urgency_score descending.
    urgency_score and recommended_tone are COMPUTED IN THE PIPELINE — not Python.
    """
    pipeline = [
        # Match overdue invoices for this creator
        {
            "$match": {
                "creator_id": creator_id,
                "status": {"$in": ["pending", "overdue", "sent"]},
                "days_overdue": {"$gt": 0},
            }
        },
        # Join with brands for payment_reliability
        {
            "$lookup": {
                "from": "brands",
                "localField": "brand_id",
                "foreignField": "_id",
                "as": "brand_data"
            }
        },
        {
            "$unwind": {
                "path": "$brand_data",
                "preserveNullAndEmptyArrays": True
            }
        },
        # Compute urgency_score and recommended_tone IN MONGODB
        {
            "$addFields": {
                "urgency_score": {
                    "$add": [
                        {"$multiply": ["$days_overdue", 0.6]},
                        {
                            "$multiply": [
                                {
                                    "$subtract": [
                                        1,
                                        {
                                            "$ifNull": [
                                                "$brand_data.payment_intelligence.payment_reliability",
                                                0.5
                                            ]
                                        }
                                    ]
                                },
                                40
                            ]
                        }
                    ]
                },
                "recommended_tone": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {"$lte": ["$days_overdue", 14]},
                                "then": "gentle"
                            },
                            {
                                "case": {"$lte": ["$days_overdue", 45]},
                                "then": "firm"
                            }
                        ],
                        "default": "final_notice"
                    }
                },
                "brand_name": {"$ifNull": ["$brand_data.name", "the brand"]},
                "brand_domain": {"$ifNull": ["$brand_data.domain", ""]},
                "brand_reliability": {
                    "$ifNull": [
                        "$brand_data.payment_intelligence.payment_reliability",
                        0.5
                    ]
                }
            }
        },
        # Sort by urgency score descending — most urgent first
        {"$sort": {"urgency_score": -1}},
        # Limit to 10 per run — don't overwhelm the creator
        {"$limit": 10},
        # Project only needed fields
        {
            "$project": {
                "_id": 1,
                "deal_id": 1,
                "amount_inr": 1,
                "days_overdue": 1,
                "urgency_score": 1,
                "recommended_tone": 1,
                "brand_name": 1,
                "brand_domain": 1,
                "brand_reliability": 1,
                "follow_ups.count": 1,
                "due_date": 1,
            }
        }
    ]

    return await db.invoices.aggregate(pipeline).to_list(10)


async def generate_followup_drafts(
    db,
    creator_id: str,
    overdue_invoices: List[dict],
) -> List[InvoiceFollowUpDraft]:
    """
    Generates tone-calibrated follow-up drafts for each overdue invoice.
    Uses the creator's voice profile for style, tone from MongoDB urgency pipeline for energy.
    """
    from backend.services.gemini_client import get_gemini_client_genai
    from backend.services.voice_compliance import evaluate_voice_compliance
    client = get_gemini_client_genai()

    creator = await db.creators.find_one({"_id": ObjectId(creator_id)})
    voice_profile = creator.get("voice_profile_brand", {}) if creator else {}

    drafts = []

    for invoice in overdue_invoices:
        invoice_id = str(invoice["_id"])
        tone = invoice["recommended_tone"]
        days = invoice["days_overdue"]
        amount = invoice.get("amount_inr")
        brand_name = invoice.get("brand_name", "the brand")
        follow_up_count = invoice.get("follow_ups", {}).get("count", 0)

        # Build context for the draft
        invoice_context = {
            "brand_name": brand_name,
            "amount_inr": f"₹{amount:,.0f}" if amount else "the agreed amount",
            "days_overdue": days,
            "follow_up_count": follow_up_count,
            "due_date": invoice.get("due_date", ""),
            "payment_deadline": (datetime.utcnow() + timedelta(
                days=5 if tone == "final_notice" else 7
            )).strftime("%B %d, %Y"),
        }

        voice_context = {
            "formality_score": voice_profile.get("formality_score", 3.0),
            "hindi_english_ratio": voice_profile.get("hindi_english_ratio", 0.0),
            "avg_response_length": voice_profile.get("avg_response_length", 80),
            "common_openers": voice_profile.get("common_openers", ["Hi,"]),
            "common_closers": voice_profile.get("common_closers", ["Best,"]),
            "top_emojis": voice_profile.get("top_emojis", []),
        }

        prompt = f"""
{TONE_PROMPTS[tone]}

Voice profile (match this writing style exactly):
{json.dumps(voice_context, indent=2)}

Invoice context:
{json.dumps(invoice_context, indent=2)}

Write the follow-up email body now.
"""

        draft_text = ""
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=FOLLOWUP_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=VOICE_GUARDIAN_SYSTEM,
                    temperature=0.2,
                    max_output_tokens=400,
                )
            )
            draft_text = response.text.strip()
        except Exception as e:
            logger.error(f"Follow-up draft error for invoice {invoice_id}: {e}")
            draft_text = f"Hi,\n\nThis is a follow-up regarding the payment of {invoice_context['amount_inr']} which is now {days} days overdue. Could you please arrange the payment at your earliest convenience?\n\nThank you."

        # Voice compliance check
        compliance = await evaluate_voice_compliance(draft_text, voice_profile)

        drafts.append(InvoiceFollowUpDraft(
            invoice_id=invoice_id,
            deal_id=str(invoice.get("deal_id", "")),
            creator_id=creator_id,
            brand_name=brand_name,
            brand_domain=invoice.get("brand_domain", ""),
            amount_inr=amount,
            days_overdue=days,
            urgency_score=round(invoice["urgency_score"], 2),
            recommended_tone=tone,
            follow_up_count=follow_up_count,
            draft_text=draft_text,
            voice_compliance_score=compliance.voice_compliance_score,
            model_used=FOLLOWUP_MODEL,
        ))

    return drafts


async def run_revenue_guardian(creator_id: str):
    """
    Main Revenue Guardian orchestrator.
    Triggered by Cloud Scheduler daily at 06:30 IST.
    Also triggerable manually via POST /guardian/run.
    """
    from backend.services.sse_manager import publish_sse_event
    from backend.database.mongodb import get_db_singleton

    db = get_db_singleton()

    logger.info(f"Revenue Guardian starting for creator {creator_id}")

    try:
        # Step 1: Run urgency aggregation in MongoDB
        overdue = await run_urgency_aggregation(db, creator_id)

        if not overdue:
            logger.info(f"No overdue invoices for creator {creator_id}. Guardian run complete.")
            return

        # Step 2: Generate drafts
        drafts = await generate_followup_drafts(db, creator_id, overdue)

        # Step 3: Store batch result in invoice_followups collection
        batch = BatchFollowUpResult(
            creator_id=creator_id,
            total_overdue=len(overdue),
            total_drafted=len(drafts),
            total_sent=0,
            total_skipped=0,
            total_recovered_inr=0.0,
            drafts=drafts,
        )

        batch_doc = batch.model_dump()
        batch_doc["drafts"] = [d.model_dump() for d in drafts]
        await write_with_classification(
            db.invoice_followups,
            batch_doc,
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

        # Step 4: Notify creator via SSE
        await publish_sse_event(creator_id, {
            "event": "guardian_ready",
            "message": f"{len(drafts)} invoice follow-up{'s' if len(drafts) > 1 else ''} ready for your review.",
            "total_overdue": len(overdue),
            "drafts_count": len(drafts),
            "has_final_notice": any(d.recommended_tone == "final_notice" for d in drafts),
        })

        # Log agent action
        await write_with_classification(
            db.agent_actions,
            {
                "creator_id": creator_id,
                "agent": "revenue_guardian",
                "action_type": AgentActionType.DRAFT_GENERATED.value,
                "execution": {"model_used": FOLLOWUP_MODEL},
                "decision": {
                    "total_overdue": len(overdue),
                    "tones_used": list(set(d.recommended_tone for d in drafts)),
                },
                "outcome": {"result": ActionResult.PENDING_APPROVAL.value},
            },
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

    except Exception as e:
        logger.error(f"Revenue Guardian error for {creator_id}: {e}", exc_info=True)
```

### 1C — Revenue Guardian router

Build in `backend/routers/guardian.py`:

```python
# backend/routers/guardian.py

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/guardian/run")
async def trigger_guardian(
    background_tasks: BackgroundTasks,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Manually triggers Revenue Guardian. Also called by Cloud Scheduler."""
    creator_id = str(current_creator["_id"])
    background_tasks.add_task(run_revenue_guardian, creator_id=creator_id)
    return {"status": "running", "message": "Checking your invoices..."}


@router.get("/guardian/pending")
async def get_pending_followups(
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Returns the latest batch of pending follow-up drafts for creator review."""
    creator_id = str(current_creator["_id"])
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
    creator_id = str(current_creator["_id"])
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
    creator_id = str(current_creator["_id"])
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
    from backend.services.gmail_sender import send_gmail_reply
    from backend.services.sse_manager import publish_sse_event
    from backend.database.mongodb import get_db_singleton
    from backend.services.calendar_service import create_followup_event

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
        from backend.models.common import AgentActionType, ActionResult, DataClassificationTier
        from backend.services.mongodb_writer import write_with_classification
        await write_with_classification(
            db.agent_actions,
            {
                "creator_id": creator_id,
                "agent": "revenue_guardian",
                "action_type": AgentActionType.EMAIL_SENT.value,
                "execution": {"model_used": FOLLOWUP_MODEL},
                "decision": {
                    "invoice_id": invoice_id,
                    "brand_name": brand_name,
                    "amount_inr": amount,
                },
                "outcome": {
                    "result": ActionResult.SUCCESS.value,
                    "gmail_message_id": sent_id,
                },
            },
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

    except Exception as e:
        logger.error(f"Send invoice follow-up error for {invoice_id}: {e}", exc_info=True)
```

### 1D — Per-outcome learning loop

When an invoice status changes to "paid", update the brand's payment intelligence. Add a Change Stream listener in `backend/database/change_streams.py`:

```python
# backend/database/change_streams.py

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def watch_invoice_payments(db):
    """
    MongoDB Change Stream: watches invoices collection for status changes to "paid".
    When an invoice is paid, updates brand payment_intelligence with actual payment days.
    This is Loop 2 (per-outcome learning) from the architecture spec.
    Run this as a long-running background task at app startup.
    """
    pipeline = [
        {
            "$match": {
                "operationType": "update",
                "updateDescription.updatedFields.status": "paid",
            }
        }
    ]

    try:
        async with db.invoices.watch(pipeline) as stream:
            async for change in stream:
                try:
                    invoice_id = change["documentKey"]["_id"]
                    invoice = await db.invoices.find_one({"_id": invoice_id})
                    if not invoice:
                        continue

                    # Calculate actual payment days
                    invoice_date = invoice.get("invoice_date") or invoice.get("created_at")
                    paid_date = invoice.get("paid_date") or datetime.utcnow()
                    if invoice_date:
                        payment_days = (paid_date - invoice_date).days
                    else:
                        payment_days = None

                    brand_id = invoice.get("brand_id")
                    if brand_id and payment_days is not None:
                        # Update brand with running average payment days
                        brand = await db.brands.find_one({"_id": brand_id})
                        if brand:
                            existing_avg = brand.get("payment_intelligence", {}).get("avg_payment_days")
                            total_paid = brand.get("payment_intelligence", {}).get("paid_count", 0)

                            if existing_avg and total_paid > 0:
                                new_avg = (existing_avg * total_paid + payment_days) / (total_paid + 1)
                            else:
                                new_avg = payment_days

                            new_reliability = min(
                                (total_paid + 1) / max((total_paid + 1) + brand.get("payment_intelligence", {}).get("overdue_count", 0), 1),
                                1.0
                            )

                            await db.brands.update_one(
                                {"_id": brand_id},
                                {
                                    "$set": {
                                        "payment_intelligence.avg_payment_days": round(new_avg, 1),
                                        "payment_intelligence.payment_reliability": round(new_reliability, 3),
                                        "updated_at": datetime.utcnow(),
                                    },
                                    "$inc": {"payment_intelligence.paid_count": 1},
                                }
                            )
                            logger.info(f"Brand {brand_id} payment intelligence updated. Avg days: {new_avg:.1f}")

                except Exception as e:
                    logger.error(f"Change stream processing error: {e}")
                    continue

    except Exception as e:
        logger.error(f"Change stream watcher died: {e}. Restarting in 30s.")
        await asyncio.sleep(30)
        asyncio.create_task(watch_invoice_payments(db))  # restart


async def start_change_streams(db):
    """Called at app startup to start all change stream watchers."""
    asyncio.create_task(watch_invoice_payments(db))
    logger.info("Change stream watchers started.")
```

Add to `backend/server.py` in the startup event:

```python
@app.on_event("startup")
async def startup_event():
    from backend.database.change_streams import start_change_streams
    from backend.database.mongodb import get_db_singleton
    db = get_db_singleton()
    await start_change_streams(db)
```

### 1E — Weekly digest (Cloud Scheduler: Monday 8AM IST)

```python
# Add to backend/routers/guardian.py

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
    if scheduler_secret != settings.WORKER_SECRET and not settings.DEBUG:
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
    from backend.services.sse_manager import publish_sse_event
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
```

---

## PART 2 — GOOGLE ADK MASTER ORCHESTRATOR

Build in `backend/services/orchestrator.py`. This is the ADK-based routing layer. For the hackathon, this is the entry point for natural language commands from the creator.

```python
# backend/services/orchestrator.py
"""
Google ADK Master Orchestrator for ThreadComb.
Routes natural language input to the correct agent via A2A protocol.
For the hackathon, implements a deterministic routing table with Gemini Flash-Lite
for disambiguation when intent is unclear.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

ROUTER_MODEL = "gemini-2.5-flash-lite"

# Deterministic routing table — covers 90% of cases without an LLM call
ROUTING_RULES = {
    # DNA Reader / Audit
    "audit": "dna_reader",
    "scan": "dna_reader",
    "analyse": "dna_reader",
    "analyze": "dna_reader",
    "read my emails": "dna_reader",
    "start audit": "dna_reader",
    "refresh": "dna_reader",
    "update skills": "dna_reader",
    # Deal Chief
    "draft": "deal_chief",
    "reply": "deal_chief",
    "respond": "deal_chief",
    "deal": "deal_chief",
    "brand deal": "deal_chief",
    "collab": "deal_chief",
    "negotiat": "deal_chief",     # negotiation, negotiate
    # Revenue Guardian
    "invoice": "revenue_guardian",
    "payment": "revenue_guardian",
    "overdue": "revenue_guardian",
    "chase": "revenue_guardian",
    "follow up": "revenue_guardian",
    "follow-up": "revenue_guardian",
    "money": "revenue_guardian",
    "owed": "revenue_guardian",
    # Multi-agent
    "everything": "all",
    "run all": "all",
    "full check": "all",
    "check everything": "all",
}

ROUTER_SYSTEM_PROMPT = """
You are routing a content creator's request to one of three AI agents:
- "dna_reader": reads email history, builds skills map, generates audit report
- "deal_chief": handles inbound brand deals, generates reply drafts
- "revenue_guardian": handles overdue invoices, generates payment follow-ups
- "all": run all three agents in sequence

Respond with a JSON object:
{"agent": "dna_reader" | "deal_chief" | "revenue_guardian" | "all", "confidence": 0.0-1.0, "reasoning": "one sentence"}
"""


def route_deterministic(user_input: str) -> tuple[str | None, float]:
    """
    Checks input against routing rules without an LLM call.
    Returns (agent_name, confidence) or (None, 0.0) if no match.
    """
    input_lower = user_input.lower()
    for keyword, agent in ROUTING_RULES.items():
        if keyword in input_lower:
            return agent, 0.95
    return None, 0.0


async def route_with_llm(user_input: str) -> tuple[str, float]:
    """
    Uses Gemini Flash-Lite to route ambiguous inputs.
    Only called when deterministic routing fails.
    """
    from backend.services.gemini_client import get_gemini_client_genai
    from google.genai import types
    client = get_gemini_client_genai()

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=ROUTER_MODEL,
            contents=f"Creator request: {user_input}",
            config=types.GenerateContentConfig(
                system_instruction=ROUTER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=100,
            )
        )
        result = json.loads(response.text)
        return result.get("agent", "dna_reader"), result.get("confidence", 0.5)
    except Exception as e:
        logger.error(f"LLM routing error: {e}")
        return "dna_reader", 0.3  # safe fallback


async def orchestrate(
    user_input: str,
    creator_id: str,
    db,
) -> AsyncGenerator[dict, None]:
    """
    Main orchestration entry point.
    Streams reasoning and progress events as an async generator.
    Used by the /orchestrate SSE endpoint.
    """
    # Step 1: Deterministic routing
    agent, confidence = route_deterministic(user_input)

    yield {
        "event": "routing",
        "message": f"Understanding your request...",
        "input": user_input,
    }

    if not agent or confidence < 0.8:
        # Step 2: LLM routing for ambiguous input
        agent, confidence = await route_with_llm(user_input)

    yield {
        "event": "routing_complete",
        "agent": agent,
        "confidence": confidence,
        "message": f"Routing to {'all agents' if agent == 'all' else agent.replace('_', ' ').title()}...",
    }

    # Step 3: Execute the routed agent(s)
    if agent == "dna_reader" or agent == "all":
        yield {"event": "agent_start", "agent": "dna_reader", "message": "DNA Reader: scanning your email history..."}
        from backend.routers.ingestion import run_full_ingestion
        # Trigger ingestion (non-blocking — progress via SSE on ingestion channel)
        asyncio.create_task(run_full_ingestion(creator_id=creator_id, job_id="orchestrated"))
        yield {"event": "agent_dispatched", "agent": "dna_reader", "message": "DNA Reader is running. Progress on the audit panel."}

    if agent == "deal_chief" or agent == "all":
        yield {"event": "agent_start", "agent": "deal_chief", "message": "Deal Chief: checking inbound brand deals..."}
        # Get unanswered deals and trigger drafts
        unanswered = await db.deals.count_documents({
            "creator_id": creator_id,
            "status": "unanswered",
        })
        if unanswered > 0:
            yield {"event": "agent_result", "agent": "deal_chief", "message": f"Found {unanswered} brand deal{'s' if unanswered > 1 else ''} needing replies. Generating drafts..."}
            unanswered_deals = await db.deals.find(
                {"creator_id": creator_id, "status": "unanswered"},
                limit=5
            ).to_list(5)
            for deal in unanswered_deals:
                asyncio.create_task(
                    run_deal_chief_for_deal(
                        deal_id=str(deal["_id"]),
                        creator_id=creator_id,
                    )
                )
        else:
            yield {"event": "agent_result", "agent": "deal_chief", "message": "No unanswered brand deals right now."}

    if agent == "revenue_guardian" or agent == "all":
        yield {"event": "agent_start", "agent": "revenue_guardian", "message": "Revenue Guardian: checking overdue invoices..."}
        overdue_count = await db.invoices.count_documents({
            "creator_id": creator_id,
            "status": {"$in": ["pending", "overdue"]},
            "days_overdue": {"$gt": 0},
        })
        if overdue_count > 0:
            yield {"event": "agent_result", "agent": "revenue_guardian", "message": f"Found {overdue_count} overdue invoice{'s' if overdue_count > 1 else ''}. Preparing follow-ups..."}
            asyncio.create_task(run_revenue_guardian(creator_id=creator_id))
        else:
            yield {"event": "agent_result", "agent": "revenue_guardian", "message": "No overdue invoices. All payments on track."}

    yield {
        "event": "orchestration_complete",
        "agent": agent,
        "message": "Done. Check each section for updates.",
    }
```

### ADK Orchestrator endpoint

Add to `backend/routers/orchestrator.py`:

```python
# backend/routers/orchestrator.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import json

router = APIRouter()


@router.get("/orchestrate")
async def orchestrate_sse(
    input: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    SSE endpoint: streams orchestrator reasoning to the frontend.
    Query param: ?input=<natural language command>
    The frontend opens an EventSource to this endpoint.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    async def generate():
        from backend.services.orchestrator import orchestrate
        async for event in orchestrate(input, creator_id, db):
            yield f"data: {json.dumps(event)}\n\n"
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/orchestrate/command")
async def orchestrate_command(
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    Non-streaming version for mobile clients or when SSE is unavailable.
    Returns a summary of what was dispatched.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    body = await request.json()
    user_input = body.get("input", "")

    from backend.services.orchestrator import route_deterministic, route_with_llm
    agent, confidence = route_deterministic(user_input)
    if not agent:
        agent, confidence = await route_with_llm(user_input)

    return {
        "routed_to": agent,
        "confidence": confidence,
        "message": f"Dispatched to {agent}. Check the relevant section for updates.",
    }
```

---

## PART 3 — COMPLETE DASHBOARD

The dashboard in Session 1 had a 4-state empty state. It now needs to be the full operational view.

Build the complete dashboard at `frontend/src/app/dashboard/page.tsx`. It has five sections:

### Dashboard layout

```
┌─────────────────────────────────────────────────────────┐
│ [ThreadComb logo]  [Creator handle + niche]  [Settings] │
├──────────────────┬──────────────────────────────────────┤
│                  │                                       │
│  Sidebar nav:    │  Main content area:                  │
│  · Overview      │  [Orchestrator command bar]           │
│  · Deals         │  [Weekly Digest Widget]               │
│  · Invoices      │  [Deal Pipeline Widget]               │
│  · Audit         │  [Invoice Tracker Widget]             │
│  · Activity      │  [Activity Feed]                      │
│  · Settings      │                                       │
└──────────────────┴──────────────────────────────────────┘
```

### 3A — Orchestrator command bar

A single text input at the top of the dashboard:

```tsx
// OrchestratorBar.tsx
// Creator types: "check my invoices" or "draft replies" or "run everything"
// On submit: opens SSE stream to /orchestrate?input=... 
// Shows streaming reasoning events as they arrive
// Small animated dots while running, checkmarks when each agent completes
```

### 3B — Deal Pipeline Widget

Fetches from `/deals/inbound`. Shows three columns:
- **Unanswered** (red badge): deals with no reply yet. "Generate Draft" button.
- **Drafts pending approval** (amber badge): drafts ready to review. "Review" button.
- **In negotiation** (blue badge): deals with a reply sent, awaiting brand response.

### 3C — Invoice Tracker Widget

Fetches from `/guardian/pending` and a direct MongoDB query. Shows:
- List of overdue invoices sorted by urgency_score (from MongoDB aggregation).
- Each row: Brand name, amount, days overdue, urgency badge (red/amber/blue), tone recommendation.
- "Review Follow-ups" button → opens batch approval modal.

### 3D — Weekly Digest Widget

Listens for `weekly_digest` SSE events. Shows:
- Paid this week: ₹X (Y invoices)
- Still outstanding: ₹X (Y invoices, Z overdue)
- Follow-ups sent: N
- Last updated: timestamp

### 3E — Activity Feed

Fetches from `/activity/recent`. Shows the last 15 `agent_actions` in reverse chronological order:
- Agent name (DNA Reader / Deal Chief / Revenue Guardian)
- Action type (human-readable label)
- Outcome (success / pending / failed)
- Timestamp

---

## PART 4 — HITL VIEWS 1 AND 4

### View 1 — Low-confidence extraction queue

Build at `frontend/src/app/dashboard/hitl/page.tsx`.

Fetches `/hitl/queue` which returns agent_actions where `action_type = "hitl_queued"` and `outcome.result = "pending_hitl"`.

For each item shows:
- Email subject
- Sender email
- Gate confidence (the Flash-Lite score)
- Reason for review
- Two buttons: "Mark as Deal Signal" (routes to extraction) / "Discard" (marks as not_deal)

Backend endpoint:

```python
# Add to backend/routers/hitl.py

@router.get("/hitl/queue")
async def get_hitl_queue(request, current_creator=Depends(get_current_creator)):
    """Returns items pending human review."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    items = await db.agent_actions.find(
        {
            "creator_id": creator_id,
            "action_type": "hitl_queued",
            "outcome.result": "pending_hitl",
        },
        sort=[("executed_at", -1)],
        limit=20
    ).to_list(20)
    for item in items:
        item["_id"] = str(item["_id"])
    return items


@router.post("/hitl/resolve/{action_id}")
async def resolve_hitl_item(action_id: str, request, current_creator=Depends(get_current_creator)):
    """Resolves a HITL queue item — either triggers extraction or discards."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    body = await request.json()
    resolution = body.get("resolution")  # "extract" or "discard"

    await db.agent_actions.update_one(
        {"_id": ObjectId(action_id), "creator_id": creator_id},
        {"$set": {
            "outcome.result": "hitl_resolved",
            "outcome.resolution": resolution,
            "outcome.resolved_at": datetime.utcnow(),
        }}
    )
    return {"status": "resolved", "resolution": resolution}
```

### View 4 — Agent Action Audit

Build at `frontend/src/app/dashboard/activity/page.tsx`.

Shows a filterable list of all agent_actions:
- Filter by agent (all / dna_reader / deal_chief / revenue_guardian)
- Filter by outcome (all / success / pending / failed)
- Each row: timestamp, agent, action, confidence score, outcome
- Expandable row: shows decision.reasoning_summary and flags_raised
- Export as JSON button (downloads all agent_actions for this creator)

---

## PART 5 — DATA EXPORT AND DELETION

### Export endpoint

```python
# Add to backend/routers/settings.py

@router.get("/settings/export")
async def export_skills_map(request, current_creator=Depends(get_current_creator)):
    """
    Exports the creator's complete Skills Map as JSON.
    DPDP data portability right — must work correctly.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    export = {
        "creator_id": creator_id,
        "exported_at": datetime.utcnow().isoformat(),
        "export_version": "1.0",
        "creator_profile": await db.creators.find_one(
            {"_id": ObjectId(creator_id)},
            {"oauth_tokens": 0, "gmail_secret_path": 0}  # exclude sensitive fields
        ),
        "deals": await db.deals.find(
            {"creator_id": creator_id},
            {"embedding_vector": 0}  # exclude vectors (not human-readable)
        ).to_list(1000),
        "brands": await db.brands.find({"data_source": {"$ne": "pre_training"}}).to_list(200),
        "invoices": await db.invoices.find({"creator_id": creator_id}).to_list(500),
        "skills_map": await db.skills_map.find({"creator_id": creator_id}).to_list(200),
        "audit_reports": await db.audit_reports.find(
            {"creator_id": creator_id},
            sort=[("created_at", -1)],
            limit=5
        ).to_list(5),
    }

    # Convert ObjectIds to strings for JSON serialization
    export = _stringify_object_ids(export)

    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": f"attachment; filename=threadcomb_export_{creator_id[:8]}.json"}
    )


@router.delete("/settings/delete-account")
async def delete_account(request, current_creator=Depends(get_current_creator)):
    """
    Permanently deletes all creator data — DPDP compliance.
    Deletes all personal_identifiable documents across all collections.
    Anonymised aggregate contributions to niche_graph are NOT deleted (legitimate basis).
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    collections_to_purge = [
        "creators", "deals", "invoices", "skills_map",
        "agent_actions", "deal_drafts", "invoice_followups",
        "audit_reports", "fan_signals", "fan_interactions",
        "fan_profiles", "response_templates",
    ]

    deletion_counts = {}
    for collection_name in collections_to_purge:
        if collection_name == "creators":
            result = await db[collection_name].delete_one({"_id": ObjectId(creator_id)})
        else:
            result = await db[collection_name].delete_many({"creator_id": creator_id})
        deletion_counts[collection_name] = result.deleted_count

    # NOTE: niche_graph documents with data_source="creator_contributed" are NOT deleted.
    # These are anonymised aggregate contributions — no PII, legitimate basis to retain.
    # The creator cannot be re-identified from these documents.

    logger.info(f"Account deletion complete for creator {creator_id}. Counts: {deletion_counts}")
    return {
        "status": "deleted",
        "message": "All your personal data has been permanently deleted from ThreadComb.",
        "deletion_counts": deletion_counts,
    }
```

---

## PART 6 — NEW COLLECTIONS AND INDEXES

Add to `backend/database/mongodb.py` in `create_indexes()`:

```python
# invoice_followups collection
await db.invoice_followups.create_index("creator_id")
await db.invoice_followups.create_index([("creator_id", 1), ("run_date", -1)])

# Add to ingestion_jobs if not already there
await db.ingestion_jobs.create_index("creator_id")

# HITL router collection (already exists as agent_actions — just adding index)
await db.agent_actions.create_index([("creator_id", 1), ("action_type", 1), ("outcome.result", 1)])
```

---

## PART 7 — CLOUD SCHEDULER CONFIGURATION

Two scheduled jobs to set up in Google Cloud Console (Cloud Scheduler):

**Job 1 — Revenue Guardian daily:**
- Name: `threadcomb-guardian-daily`
- Schedule: `30 1 * * *` (1:30 AM UTC = 7:00 AM IST)
- Target: Cloud Run HTTP POST → `/api/guardian/run`
- Auth: OIDC token for the Cloud Run service account
- Body: `{"scheduled": true}`

**Job 2 — Weekly digest Mondays:**
- Name: `threadcomb-weekly-digest`
- Schedule: `30 2 * * 1` (2:30 AM UTC Monday = 8:00 AM IST Monday)
- Target: Cloud Run HTTP POST → `/api/guardian/weekly-digest/all`
- Auth: OIDC token
- Note: The `/weekly-digest/all` endpoint (not built above) iterates over all active creators and calls weekly digest for each. Add this endpoint.

**Job 3 — Gmail watch renewal:**
- Name: `threadcomb-gmail-watch-renewal`
- Schedule: `0 0 */6 * *` (every 6 days at midnight UTC)
- Target: Cloud Run HTTP POST → `/api/ingestion/renew-watches`
- Note: Gmail watch expires after 7 days. This renews it.

---

## PART 8 — REGISTER ALL NEW ROUTERS

Update `backend/server.py` to register all new routers:

```python
from backend.routers.guardian import router as guardian_router
from backend.routers.orchestrator import router as orchestrator_router
from backend.routers.hitl import router as hitl_router
from backend.routers.settings import router as settings_router

app.include_router(guardian_router, prefix="/api")
app.include_router(orchestrator_router, prefix="/api")
app.include_router(hitl_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
```

---

## PART 9 — HACKATHON DEMO PREPARATION

This is not optional. The hackathon submission requires a 3-minute demo video and a live URL.

### Demo data setup script

Build `backend/database/seed_demo.py` — creates a realistic pre-staged demo environment:

```python
# backend/database/seed_demo.py
"""
Seeds a demo creator account with realistic brand deal history.
Use this to populate the demo environment for the hackathon video.
Run: python backend/database/seed_demo.py

Creates:
- 1 demo creator (ananya.creates.demo@threadcomb.com)
- 20 brand deal emails (mix of unanswered, negotiating, paid, overdue)
- 5 brands (Minimalist, Mamaearth, boAt, Unacademy, Zomato)
- 3 overdue invoices
- A pre-generated Audit Report showing ₹2,25,000 in recoverable value
- 2 pending deal drafts ready for approval
"""

DEMO_DEALS = [
    {
        "brand_name": "Minimalist",
        "brand_domain": "beminimalist.co",
        "brand_category": "beauty",
        "deal_type": "instagram_reel",
        "status": "unanswered",
        "financials": {"amount_inr": 45000, "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 Instagram Reel", "2 Stories"], "exclusivity_mentioned": True, "exclusivity_duration_days": 90},
        "extraction_confidence": 0.92,
        "thread_unanswered": True,
    },
    {
        "brand_name": "boAt",
        "brand_domain": "boat-lifestyle.com",
        "brand_category": "tech",
        "deal_type": "youtube_integration",
        "status": "overdue",
        "financials": {"amount_inr": 120000, "amount_ambiguity_flag": False, "currency": "INR"},
        "raw_signals": {"deliverables": ["1 YouTube Integration (60 sec)"], "payment_terms_mentioned": "NET-30"},
        "extraction_confidence": 0.89,
    },
    # Add 18 more deals covering all statuses and brands
    # Include 1-2 with amount_ambiguity_flag=True to demonstrate the ambiguity system
]

DEMO_INVOICES = [
    {
        "brand_name": "boAt",
        "amount_inr": 120000,
        "days_overdue": 47,
        "status": "overdue",
        "follow_ups": {"count": 0},
    },
    {
        "brand_name": "Zomato",
        "amount_inr": 65000,
        "days_overdue": 21,
        "status": "overdue",
        "follow_ups": {"count": 1},
    },
    {
        "brand_name": "Unacademy",
        "amount_inr": 40000,
        "days_overdue": 8,
        "status": "pending",
        "follow_ups": {"count": 0},
    },
]
```

### 3-minute demo script

```
00:00–00:30 — The problem
"Ananya has 85,000 Instagram followers and earns from brand deals.
Last month she left ₹2,25,000 on the table without knowing it."

00:30–01:15 — Audit Report (Session 3)
"Connect Gmail. ThreadComb reads 6 months of emails.
[Show: ingestion progress + First Signal appearing]
[Show: Audit Report with findings — ₹2,25,000 unanswered deals]"

01:15–02:00 — Deal Chief (Session 4)
"A new Myntra email arrives.
[Show: new_deal_detected SSE event fires]
[Show: draft_ready SSE event — 8 seconds later]
[Show: ShadowDraftModal with brand score, flags, voice-matched draft]
[Show: creator taps Approve & Send — email appears in Gmail Sent]"

02:00–02:45 — Revenue Guardian (Session 5)
"boAt owes ₹1,20,000 for 47 days.
[Show: Guardian runs — urgency pipeline in MongoDB]
[Show: batch approval UI — 3 follow-ups with different tones]
[Show: creator approves — Calendar reminder created]"

02:45–03:00 — The MongoDB moment
"All of this runs on MongoDB Atlas.
[Show: Atlas UI — deals collection with vectors, brands with payment intelligence]
[Show: aggregation pipeline results — the urgency_score calculation]
Not AI guessing. Real data. Your own business intelligence."
```

---

## EXIT CRITERIA — ALL MUST PASS BEFORE HACKATHON SUBMISSION

1. **Revenue Guardian urgency aggregation runs in MongoDB:** Run `run_urgency_aggregation()` with at least 2 overdue invoices in MongoDB. Confirm the returned documents have `urgency_score` and `recommended_tone` fields set — computed by the aggregation pipeline, not Python.

2. **Three tones produce distinct drafts:** For invoices with `days_overdue` = 7, 30, and 60 respectively, confirm the three generated drafts are noticeably different in length and tone (gentle, firm, final_notice).

3. **Batch approval sends real emails:** POST `/guardian/approve-batch` with one invoice ID. Confirm email appears in Gmail Sent folder. Confirm `invoices.follow_ups.count` increments. Confirm Calendar event created.

4. **Change stream listener starts:** Check application logs at startup for "Change stream watchers started." Mark an invoice status as "paid" manually in Atlas. Confirm the brand's `payment_intelligence.avg_payment_days` updates within 30 seconds.

5. **Orchestrator routes correctly:** POST `/orchestrate/command` with body `{"input": "check my invoices"}`. Confirm response contains `{"routed_to": "revenue_guardian"}`. POST with `{"input": "reply to Myntra email"}`. Confirm `{"routed_to": "deal_chief"}`.

6. **Orchestrator SSE streams:** Open EventSource to `/orchestrate?input=run+everything`. Confirm events stream in sequence: routing → routing_complete → agent_start (×3) → orchestration_complete.

7. **Dashboard shows all 5 widgets:** With demo data seeded, confirm the dashboard shows: orchestrator bar, deal pipeline widget (with deal counts), invoice tracker (sorted by urgency), weekly digest widget, activity feed (last 15 actions).

8. **HITL View 1 shows queue:** With at least one low-confidence thread in `agent_actions`, confirm `/hitl/queue` returns it and the UI renders it with "Mark as Deal Signal" and "Discard" buttons.

9. **Data export works:** GET `/settings/export`. Confirm the response is valid JSON. Confirm it contains `deals`, `invoices`, `skills_map` arrays. Confirm `embedding_vector` is excluded from deals.

10. **Data deletion works:** POST `/settings/delete-account` for a test creator. Confirm all collections return 0 documents for that `creator_id`. Confirm `niche_graph` documents with `data_source: "pre_training"` are NOT deleted.

11. **Demo seed script runs:** `python backend/database/seed_demo.py` completes without errors. Confirm 20 deals, 3 invoices, 5 brands exist in MongoDB under the demo creator ID.

12. **No send outside approval endpoints:** Search codebase for calls to `send_gmail_reply()`. Confirm it is only called from: `/deals/approve/{deal_id}` and `send_invoice_followup()` (which is itself only called from `/guardian/approve-batch` and `/guardian/approve-single/{invoice_id}`). ACTION_POLICY structural constraint maintained.

---

## NOTES FOR you

- `invoice_followups` is a new collection — add to `create_indexes()`.
- The Change Stream watcher must be started as an `asyncio.create_task()` at app startup, not as a FastAPI background task. Background tasks are tied to request lifecycle. Change streams need to run for the life of the application.
- MongoDB M0 (free tier) does NOT support Change Streams on shared clusters in some regions. If Change Streams fail with "not supported on free tier," use a polling fallback: Cloud Scheduler calls a `/invoices/update-payment-status` endpoint every hour that queries for status changes. Document this workaround.
- The orchestrator imports from routers (deal_chief router's `run_deal_chief_for_deal`). Use lazy imports inside the function body to avoid circular import issues.
- Cloud Scheduler requires Cloud Run to have a public URL. During local dev, the weekly digest and guardian daily jobs cannot be tested via Scheduler — call the endpoints directly.
- `_stringify_object_ids()` helper for the export endpoint: write a recursive function that converts all `ObjectId` and `datetime` objects to strings in a nested dict/list structure.
- The demo seed script should be idempotent: check if the demo creator email already exists before creating. Use upsert logic throughout.
- All new router files need `get_current_creator`, `get_db_singleton`, and `ObjectId` imports — check that these match the existing pattern in `backend/routers/deals.py`.
- `FOLLOWUP_MODEL = "gemini-2.5-flash"` — do NOT use Pro for follow-up drafts. The content is short and structured. Flash is sufficient and significantly cheaper.

---

*ThreadComb Session 5 — all three agents live. Orchestrator routing. Complete dashboard.*
*A creator connects Gmail. ThreadComb reads everything, drafts replies, chases invoices.*
*That is the product. That is the hackathon submission.*
