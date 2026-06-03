import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import List
from bson import ObjectId
from google.genai import types

from models.invoice import InvoiceFollowUpDraft, BatchFollowUpResult
from models.common import DataClassificationTier, AgentActionType, ActionResult
from services.mongodb_writer import write_with_classification

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
    from services.gemini_client import get_gemini_client_genai
    from services.voice_compliance import evaluate_voice_compliance
    client = get_gemini_client_genai()

    creator = await db.creators.find_one({"creator_id": creator_id})
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
        due_date = invoice.get("due_date", "")
        if hasattr(due_date, "isoformat"):
            due_date = due_date.strftime("%B %d, %Y")
        invoice_context = {
            "brand_name": brand_name,
            "amount_inr": f"₹{amount:,.0f}" if amount else "the agreed amount",
            "days_overdue": days,
            "follow_up_count": follow_up_count,
            "due_date": str(due_date),
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
    from services.sse_manager import publish_sse_event
    from database.mongodb import get_db_singleton

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
