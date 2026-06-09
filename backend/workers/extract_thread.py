"""Full Gemini extraction worker — replaces the Session 2B stub.

Called by:
  - Cloud Tasks via POST /workers/extract-thread
  - Dev trigger via POST /workers/trigger-direct
  - Dev trigger via POST /ingestion/trigger-dev-extraction/{job_id}

Produces:
  - A deals MongoDB document
  - An upserted brands MongoDB document
  - A gemini-embedding-2 vector on the deal
  - Skills Map preference nodes (if evidence threshold met)
  - HITL queue entry (if confidence below threshold)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from models.deal import DealExtraction
from models.common import DataClassificationTier, AgentActionType, ActionResult
from database.mongodb import get_db_singleton
from services.mongodb_writer import write_with_classification
from services.gemini_client import get_gemini_client_genai, GeminiClient

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = GeminiClient.DEFAULT_MODEL
EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIMENSIONS = 768

# ── Extraction system prompt ──────────────────────────────────────────────────

DEAL_EXTRACTION_SYSTEM_PROMPT = """\
You are extracting structured data from brand deal email threads sent to Indian content creators.

Your task: Analyse the full email thread and extract deal signals into the provided JSON schema.

CRITICAL RULES — FOLLOW EXACTLY:

1. FINANCIAL AMOUNTS:
   - If the amount is stated as a specific number or clear range: extract it. Set amount_ambiguity_flag=false.
   - If the amount is informal, vague, or not stated: set amount_ambiguity_flag=true. Set amount_min, amount_max, amount_typical to NULL. Never guess.
   - Ambiguous expressions: "50 hazaar", "do lakh", "let's discuss", "competitive budget", "as per rate card", "negotiable" → all trigger ambiguity_flag=true.
   - Convert informal Indian number expressions to digits when unambiguous: "50 thousand" → 50000, "1.5 lakh" → 150000.

2. DEAL STATUS:
   - Read the ENTIRE thread, not just the first email. Status must reflect the latest state.
   - If the thread has multiple messages and the creator never replied → "unanswered".
   - If the creator replied with a counter-offer → "negotiating".
   - If both parties agreed on terms → "accepted".

3. BRAND DOMAIN:
   - Extract from the sender's email address (everything after @).
   - If a PR agency is sending on behalf of a brand, set is_agency_contact=true and try to identify the actual brand from the email body.

4. HINDI/MIXED CONTENT:
   - If the email contains Hindi (Devanagari or Roman transliteration) set hindi_mode=true.
   - Still extract all fields — Hindi emails follow the same schema.

5. EXTRACTION CONFIDENCE:
   - 0.90+: all key fields extracted with high certainty
   - 0.70–0.89: most fields extracted, some uncertainty
   - 0.50–0.69: significant uncertainty — set requires_human_review=true
   - Below 0.50: unable to extract meaningfully — set requires_human_review=true, leave most fields null

6. RESPONSE TIME:
   - If you can see timestamps in the thread and the creator replied, calculate creator_response_time_hrs.
   - If the creator never replied: set thread_unanswered=true.

Return valid JSON matching the DealExtraction schema. No markdown. No explanation. JSON only.
"""


async def run_extraction_worker(payload: dict):
    """
    Core extraction function. Called by:
    - Cloud Tasks via POST /workers/extract-thread
    - Dev trigger via POST /workers/trigger-direct
    - Dev trigger via POST /ingestion/trigger-dev-extraction/{job_id}

    Takes a sanitised thread payload and produces:
    - A deals MongoDB document
    - An upserted brands MongoDB document
    - A gemini-embedding-2 vector on the deal
    - Skills Map preference nodes (if evidence threshold met)
    - HITL queue entry (if confidence below threshold)
    """
    db = get_db_singleton()

    thread_id = payload.get("thread_id", "")
    creator_id = payload.get("creator_id", "")
    job_id = payload.get("job_id", "")
    sanitised_text = payload.get("sanitised_text", "")
    sender_email = payload.get("sender_email", "")
    subject = payload.get("subject", "")
    date_range_start = payload.get("date_range_start", "")
    hindi_mode = payload.get("hindi_mode", False)
    has_attachments = payload.get("has_attachments", False)
    attachment_names = payload.get("attachment_names", [])

    if not sanitised_text or not creator_id:
        logger.warning(f"Worker received empty payload for thread {thread_id}")
        return

    # DLQ Tracking (Step 1: Fetch or create task)
    task = await db.ingestion_tasks.find_one({"thread_id": thread_id, "job_id": job_id})
    if not task:
        task = {
            "thread_id": thread_id,
            "creator_id": creator_id,
            "job_id": job_id,
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "raw_payload": payload,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        res = await db.ingestion_tasks.insert_one(task)
        task_id = res.inserted_id
        task["_id"] = task_id
    else:
        task_id = task["_id"]
        if task.get("status") in ["completed", "dead_letter"]:
            logger.info(f"Task {task_id} already completed or quarantined.")
            return

    # Advance state to processing
    await db.ingestion_tasks.update_one(
        {"_id": task_id},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}}
    )

    try:
        # ── Step 1: Gemini Flash extraction ──────────────────────────────────
        extraction = await _run_deal_extraction(
            sanitised_text=sanitised_text,
            sender_email=sender_email,
            subject=subject,
            thread_id=thread_id,
            hindi_mode=hindi_mode,
        )

        # ── Step 2: Route low-confidence extractions to HITL ─────────────────
        if extraction.requires_human_review or extraction.extraction_confidence < 0.50:
            await _queue_for_hitl(db, creator_id, thread_id, subject, sender_email, extraction, job_id)
            return

        # ── Step 3: Upsert brand document ────────────────────────────────────
        brand_id = await _upsert_brand(db, extraction)

        # ── Step 4: Generate embedding ────────────────────────────────────────
        embedding_vector = await _generate_embedding(extraction, subject)

        # ── Step 5: Write deal document to MongoDB ────────────────────────────
        deal_id = await _write_deal(db, creator_id, brand_id, extraction, embedding_vector, thread_id, date_range_start)

        # ── Step 6: Update skills_map preference nodes ────────────────────────
        await _update_skills_map(db, creator_id, extraction, deal_id)

        # ── Step 7: Voice profile contribution (outbound analysis) ──────────
        # Voice profile is extracted from outbound emails — see voice_profiler.py

        # ── Step 8: Update job progress ──────────────────────────────────────
        if job_id:
            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id), "thread_statuses.thread_id": thread_id},
                {
                    "$inc": {"threads_extraction_complete": 1},
                    "$set": {
                        "updated_at": datetime.now(timezone.utc),
                        "thread_statuses.$.extraction_complete": True
                    }
                }
            )
            await _check_and_trigger_audit(db, job_id, creator_id)

        # ── Step 9: Log agent action ──────────────────────────────────────────
        await write_with_classification(
            db.agent_actions,
            {
                "creator_id": creator_id,
                "agent": "dna_reader",
                "action_type": AgentActionType.INGESTION_COMPLETE.value,
                "execution": {
                    "model_used": EXTRACTION_MODEL,
                    "confidence": extraction.extraction_confidence,
                    "thread_id": thread_id,
                },
                "decision": {
                    "reasoning_summary": f"Extracted {extraction.deal_type or 'unknown'} deal from {extraction.brand_name or sender_email}",
                    "flags_raised": ["amount_ambiguous"] if extraction.amount_ambiguity_flag else [],
                },
                "outcome": {"result": ActionResult.SUCCESS.value},
            },
            classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
        )

        # ── Finalize success state mark ───────────────────────────────────────
        await db.ingestion_tasks.update_one(
            {"_id": task_id},
            {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}}
        )
        logger.info(f"Extraction complete: thread={thread_id} brand={extraction.brand_name} deal_id={deal_id}")

        # ── Step 10 (Session 4): Trigger Deal Chief for automatic draft ───────
        try:
            from routers.deals import run_deal_chief_for_deal
            asyncio.create_task(
                run_deal_chief_for_deal(deal_id=deal_id, creator_id=creator_id)
            )
            logger.info(f"Deal Chief triggered for deal {deal_id}")
        except Exception as e:
            logger.warning(f"Deal Chief trigger failed (non-critical): {e}")

    except Exception as exc:
        error_msg = str(exc)
        current_retries = task.get("retry_count", 0) + 1
        max_allowed = task.get("max_retries", 3)
        error_entry = {"attempt": current_retries, "error": error_msg, "timestamp": datetime.now(timezone.utc)}

        if current_retries >= max_allowed:
            # === DEVIATION TO DEAD-LETTER QUEUE ===
            await db.ingestion_tasks.update_one(
                {"_id": task_id},
                {
                    "$set": {"status": "dead_letter", "last_error": error_msg, "updated_at": datetime.now(timezone.utc)},
                    "$push": {"error_history": error_entry}
                }
            )
            logger.critical(f"Task {task_id} exceeded max retries. EVACUATED TO DLQ. Reason: {error_msg}")
            
            # Still update job error count
            if job_id:
                await db.ingestion_jobs.update_one(
                    {"_id": ObjectId(job_id)},
                    {"$inc": {"threads_errored": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}}
                )
                await _check_and_trigger_audit(db, job_id, creator_id)
        else:
            # === SCHEDULE NEXT RETRY CYCLE ===
            await db.ingestion_tasks.update_one(
                {"_id": task_id},
                {
                    "$set": {"status": "pending", "retry_count": current_retries, "last_error": error_msg, "updated_at": datetime.now(timezone.utc)},
                    "$push": {"error_history": error_entry}
                }
            )
            logger.warning(f"Task {task_id} failed on attempt {current_retries}/{max_allowed}. Re-queued. Error: {error_msg}")
            raise exc # Re-raise to trigger Cloud Tasks retry mechanisms


async def _run_deal_extraction(
    sanitised_text: str,
    sender_email: str,
    subject: str,
    thread_id: str,
    hindi_mode: bool,
) -> DealExtraction:
    """Calls Gemini Flash with structured output schema."""
    from services.gemini_client import get_gemini_client_genai
    from google.genai import types

    client = get_gemini_client_genai()

    prompt = f"""
Subject: {subject}
From: {sender_email}
Hindi/mixed content: {hindi_mode}

Full email thread:
{sanitised_text}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=EXTRACTION_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=DEAL_EXTRACTION_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=DealExtraction,
            temperature=0.0,
            max_output_tokens=8192,
        )
    )

    if response.parsed:
        result = response.parsed
    else:
        raise ValueError("Model completed successfully but output schema execution failed.")
    result.gmail_thread_id = thread_id
    result.sender_email = sender_email
    result.subject = subject
    result.hindi_mode = hindi_mode
    return result


async def _generate_embedding(extraction: DealExtraction, subject: str) -> list[float]:
    """
    Generates a normalized 768d embedding for the deal using gemini-embedding-2.
    IMPORTANT: gemini-embedding-2 at 768d is NOT pre-normalized.
    We normalize manually before storing. Without normalization,
    cosine similarity queries return incorrect results.
    """
    from services.gemini_client import get_gemini_client_genai
    from google.genai import types
    from math import sqrt

    client = get_gemini_client_genai()

    # Embed a rich text representation of the deal — not just the email
    embed_text = " ".join(filter(None, [
        extraction.brand_name,
        extraction.brand_category,
        extraction.deal_type,
        subject,
        " ".join(extraction.deliverables),
        extraction.exclusivity_scope,
        extraction.payment_terms_mentioned,
    ]))

    if not embed_text.strip():
        return [0.0] * EMBEDDING_DIMENSIONS

    response = await asyncio.to_thread(
        client.models.embed_content,
        model=EMBEDDING_MODEL,
        contents=embed_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",    # indexing — use RETRIEVAL_QUERY when searching
            output_dimensionality=EMBEDDING_DIMENSIONS,
        )
    )

    vector = response.embeddings[0].values

    # NORMALIZE — required for 768d (only 3072d is pre-normalized by API)
    # Using pure Python to avoid hard numpy dependency
    norm = sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


async def _upsert_brand(db, extraction: DealExtraction) -> Optional[str]:
    """Upserts brand document. Returns brand _id as string."""
    if not extraction.brand_domain and not extraction.brand_name:
        return None

    lookup_key = extraction.brand_domain or extraction.brand_name.lower().replace(" ", "")

    brand_doc = {
        "name": extraction.brand_name or lookup_key,
        "domain": extraction.brand_domain or "",
        "category": extraction.brand_category or "other",
        "updated_at": datetime.now(timezone.utc),
    }

    # Running payment intelligence update (only if we have payment data)
    update_set = dict(brand_doc)
    if extraction.payment_days:
        update_set["payment_intelligence.last_seen_payment_days"] = extraction.payment_days

    or_clauses = []
    if extraction.brand_domain:
        or_clauses.append({"domain": extraction.brand_domain})
    if extraction.brand_name:
        or_clauses.append({"name": {"$regex": f"^{extraction.brand_name}$", "$options": "i"}})

    if not or_clauses:
        return None

    await db.brands.update_one(
        {"$or": or_clauses},
        {
            "$set": update_set,
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
                # Use dot-path to avoid conflict with $set/$inc on payment_intelligence.*
                "payment_intelligence.payment_reliability": 0.5,
                "payment_intelligence.avg_payment_days": None,
                "data_classification": {
                    "tier": "anonymisable",
                    "anonymisation_eligible": True,
                    "export_eligible": True,
                },
                "data_source": "gmail_ingestion",
            },
            "$inc": {"payment_intelligence.total_deals_on_platform": 1},
        },
        upsert=True
    )

    brand = await db.brands.find_one(
        {"$or": or_clauses}
    )
    return str(brand["_id"]) if brand else None


async def _write_deal(
    db, creator_id: str, brand_id: Optional[str],
    extraction: DealExtraction, embedding_vector: list,
    thread_id: str, date_range_start: str
) -> str:
    """Writes the deals document. Returns deal _id as string."""
    deal_doc = {
        "creator_id": creator_id,
        "brand_id": brand_id,
        "financials": {
            "amount": extraction.amount_typical,
            "amount_min": extraction.amount_min,
            "amount_max": extraction.amount_max,
            "amount_raw_text": extraction.amount_raw_text,
            "amount_ambiguity_flag": extraction.amount_ambiguity_flag,
            "currency": extraction.currency,
            "amount_inr": extraction.amount_typical,   # same for INR deals
            "payment_terms": extraction.payment_terms_mentioned,
            "payment_days": extraction.payment_days,
        },
        "status": extraction.deal_status,
        "deal_type": extraction.deal_type,
        "raw_signals": {
            "exclusivity_mentioned": extraction.exclusivity_mentioned,
            "exclusivity_scope": extraction.exclusivity_scope,
            "exclusivity_duration_days": extraction.exclusivity_duration_days,
            "deliverables": extraction.deliverables,
            "timeline_days": extraction.timeline_days,
            "brand_contact_email": extraction.brand_contact_email,
            "gmail_thread_id": thread_id,
            "is_agency_contact": extraction.is_agency_contact,
            "platform": "gmail",
        },
        "response_time_hrs": extraction.creator_response_time_hrs,
        "thread_unanswered": extraction.thread_unanswered,
        "initiated_at": date_range_start or datetime.now(timezone.utc).isoformat(),
        "extraction_confidence": extraction.extraction_confidence,
        "requires_human_review": extraction.requires_human_review,
        "embedding_vector": embedding_vector,
        "embedding_model": f"{EMBEDDING_MODEL}-{EMBEDDING_DIMENSIONS}d",
        "anonymisation_eligible": True,
        "niche_snapshot": None,         # filled by a separate creator lookup
        "follower_tier_snapshot": None,  # filled by a separate creator lookup
        "data_classification": {
            "tier": "personal_identifiable",
            "deletion_policy": "on_request_30d",
            "anonymisation_eligible": True,
            "export_eligible": True,
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = await db.deals.insert_one(deal_doc)
    return str(result.inserted_id)


async def _update_skills_map(db, creator_id: str, extraction: DealExtraction, deal_id: str):
    """
    Updates skills_map preference nodes based on this extraction.
    Only updates if evidence is unambiguous — never infers preferences.
    Evidence accumulation: each confirmed data point increments evidence.count.
    Confidence is computed as min(count / 10, 1.0) per the spec.
    """
    nodes_to_update = []

    # Brand category preference
    if extraction.brand_category and extraction.deal_status in ("accepted", "paid", "delivered"):
        nodes_to_update.append(("preference", f"prefers_{extraction.brand_category}_brands", "PREFER", extraction.brand_category))

    # Exclusivity pattern
    if extraction.exclusivity_mentioned and extraction.exclusivity_duration_days:
        if extraction.deal_status in ("accepted", "paid", "delivered"):
            nodes_to_update.append(("pattern", "accepts_exclusivity", None, str(extraction.exclusivity_duration_days)))

    for node_type, name, polarity, value in nodes_to_update:
        await db.skills_map.update_one(
            {"creator_id": creator_id, "name": name},
            {
                "$set": {
                    "type": node_type,
                    "description": "Inferred from brand deal history",
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {
                    "creator_id": creator_id,
                    "name": name,
                    "preference.polarity": polarity,
                    "preference.value": value,
                    "preference.strength": 0.0,
                    "preference.effective_strength": 0.0,
                    "evidence.count": 0,
                    "evidence.confidence": 0.0,
                    "evidence.decay_rate": 0.002,
                    "created_at": datetime.now(timezone.utc),
                    "anonymisation_eligible": True,
                },
                "$inc": {"evidence.count": 1},
            },
            upsert=True
        )
        # Recompute confidence after increment
        node = await db.skills_map.find_one({"creator_id": creator_id, "name": name})
        if node:
            count = node.get("evidence", {}).get("count", 1)
            confidence = min(count / 10, 1.0)
            strength = round(confidence * 0.9, 3)  # max 0.9 without human confirmation
            await db.skills_map.update_one(
                {"creator_id": creator_id, "name": name},
                {"$set": {
                    "evidence.confidence": confidence,
                    "preference.strength": strength,
                    "preference.effective_strength": strength,
                    "evidence.last_observed": datetime.now(timezone.utc),
                }}
            )


async def _queue_for_hitl(db, creator_id: str, thread_id: str, subject: str, sender_email: str, extraction: DealExtraction, job_id: str):
    """Routes low-confidence extractions to HITL View 1 queue."""
    await write_with_classification(
        db.agent_actions,
        {
            "creator_id": creator_id,
            "agent": "dna_reader",
            "action_type": AgentActionType.HITL_QUEUED.value,
            "execution": {
                "model_used": EXTRACTION_MODEL,
                "confidence": extraction.extraction_confidence,
                "thread_id": thread_id,
            },
            "decision": {
                "reasoning_summary": extraction.review_reason or "Low extraction confidence",
                "subject": subject,
                "sender_email": sender_email,
                "amount_ambiguous": extraction.amount_ambiguity_flag,
                # NOTE: sanitised_text is NOT stored — HITL sees only metadata
            },
            "outcome": {"result": ActionResult.PENDING_HITL.value},
        },
        classification_tier=DataClassificationTier.PERSONAL_IDENTIFIABLE,
    )
    if job_id:
        await db.ingestion_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$inc": {"threads_low_confidence": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}}
        )
        await _check_and_trigger_audit(db, job_id, creator_id)

async def _check_and_trigger_audit(db, job_id: str, creator_id: str):
    """Check if all threads are processed, and trigger audit if true."""
    job = await db.ingestion_jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        return
        
    queued = job.get("threads_queued_for_extraction", 1)
    processed = (
        job.get("threads_extraction_complete", 0) +
        job.get("threads_low_confidence", 0) +
        job.get("threads_errored", 0)
    )
    
    if processed >= queued:
        # Prevent triggering multiple times if somehow we exceed
        # We can check a flag
        if not job.get("audit_generation_triggered"):
            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"audit_generation_triggered": True, "updated_at": datetime.now(timezone.utc)}}
            )
            from routers.audit import run_audit_generation
            asyncio.create_task(run_audit_generation(creator_id=creator_id))
            logger.info(f"All extractions complete for job {job_id}. Triggered audit generation.")
