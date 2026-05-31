# THREADCOMB — SESSION 3 PROMPT
# DNA Reader Agent + First Signal Module
# Next.js 15 + React 19, FastAPI, MongoDB Atlas, Google ADK
# Paste this entire document to Copilot Agent as context. Work through it section by section.

---

## IDENTITY ANCHOR — READ THIS FIRST

**Product:** ThreadComb — AI-powered creator operations platform.
**Stack:** Next.js 15 + React 19 (App Router, TypeScript) + FastAPI (Python 3.11, Pydantic v2, motor) + MongoDB Atlas M0 (Mumbai) + Google ADK + Gemini API.
**What exists from Sessions 1–2B:**
- MongoDB Atlas: 10 collections live, Atlas Vector Search index on deals.embedding_vector (768d cosine, gemini-embedding-2 normalised).
- FastAPI: Gmail OAuth, ingestion pipeline (fetch → sanitise → gate classify → Cloud Tasks enqueue), SSE streaming, /workers/extract-thread stub (returns 200).
- React: Auth, 4-step onboarding, mocked Gmail connect button (real OAuth wired), empty dashboard with "Start Your Audit" button disabled.
- Cloud Tasks: Queue live, tasks enqueue correctly. Worker needs public URL to receive tasks (ngrok or Cloud Run). Dev workaround: direct trigger endpoint (built in this session).
- No real creator data in MongoDB yet.

**Session 3 builds:**
1. The Cloud Tasks worker — full Gemini extraction replacing the stub
2. DealExtraction + ContractExtraction Pydantic schemas
3. gemini-embedding-2 at 768d with normalization
4. MongoDB writes: deals, brands upsert, skills_map preference nodes
5. Voice profile extraction (brand register only)
6. 3 MongoDB aggregation pipelines for Audit Report
7. Gemini Pro synthesis → Audit Report markdown → PDF → Cloud Storage
8. Wire "Start Your Audit" button — enables after Gmail connected
9. **First Signal module** — immediate value before full audit completes
10. Dev workaround: direct extraction trigger for localhost testing

**Does NOT build in Session 3:**
- Fan Management Agent (Phase 2, needs Instagram App Review)
- Deal Chief reply drafting (Session 4)
- Revenue Guardian invoice chasing (Session 5)
- Full Loyalty Graph (Phase 2)

---

## PART 1 — DEV WORKAROUND FOR CLOUD TASKS LOCALHOST

Cloud Tasks cannot call localhost. Add this dev-only endpoint so extraction can be tested without ngrok or Cloud Run during development.

### New endpoint: POST /workers/trigger-direct

```python
# In backend/routers/workers.py — add alongside the Cloud Tasks endpoint

@router.post("/workers/trigger-direct")
async def trigger_extraction_direct(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    DEV ONLY — bypasses Cloud Tasks, calls extraction logic directly.
    Use this for local testing when Cloud Tasks cannot reach localhost.
    Remove or gate behind DEBUG flag before production deployment.
    Accepts same payload as /workers/extract-thread.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Only available in DEBUG mode")

    body = await request.json()
    background_tasks.add_task(run_extraction_worker, payload=body)
    return {"status": "triggered", "mode": "direct", "thread_id": body.get("thread_id")}
```

Also add a helper on the ingestion router:

```python
# In backend/routers/ingestion.py — add after /ingestion/start

@router.post("/ingestion/trigger-dev-extraction/{job_id}")
async def trigger_dev_extraction(
    job_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """
    DEV ONLY — pulls queued threads from ingestion_jobs and sends them
    directly to run_extraction_worker, bypassing Cloud Tasks.
    Use when running locally without a public WORKER_BASE_URL.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Only available in DEBUG mode")

    db = get_db_singleton()
    creator_id = str(current_creator["_id"])
    job = await db.ingestion_jobs.find_one({"_id": ObjectId(job_id), "creator_id": creator_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Directly call extraction on each queued thread_id
    # In dev: thread payloads are stored in job.thread_statuses
    # Re-fetch thread content and run extraction inline
    triggered = 0
    for ts in job.get("thread_statuses", []):
        if ts.get("queued_for_extraction") and not ts.get("extraction_complete"):
            # Re-run gate → extraction pipeline directly
            from backend.workers.extract_thread import run_extraction_worker
            background_tasks.add_task(run_extraction_worker, thread_status=ts, creator_id=creator_id, job_id=job_id)
            triggered += 1

    return {"status": "ok", "threads_triggered": triggered, "mode": "dev_direct"}
```

---

## PART 2 — PYDANTIC EXTRACTION SCHEMAS

These are the exact schemas for Gemini structured output. Build in `backend/models/deal.py`.

```python
# backend/models/deal.py — complete file

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class DealExtraction(BaseModel):
    """
    Output schema for Gemini Flash extraction of a single brand deal email thread.
    Used with response_mime_type='application/json' and response_schema=DealExtraction.
    Every field has a default — extraction must never fail due to missing fields.
    """

    # Brand identification
    brand_name: Optional[str] = None
    brand_domain: Optional[str] = None          # extracted from sender email if not stated
    brand_category: Optional[str] = None         # beauty | gaming | edtech | fintech | fashion | fmcg | tech | food | sports | wellness | other

    # Deal type
    deal_type: Optional[Literal[
        "instagram_reel", "instagram_post", "instagram_story",
        "youtube_dedicated", "youtube_integration", "youtube_shorts",
        "multi_platform", "other"
    ]] = None

    # Financial signals
    amount_raw_text: Optional[str] = None        # exact text from email mentioning money
    amount_ambiguity_flag: bool = False          # True if amount is informal/unclear
    amount_min: Optional[float] = None          # None if ambiguous
    amount_max: Optional[float] = None          # None if ambiguous
    amount_typical: Optional[float] = None      # best single estimate if stated
    currency: str = "INR"

    # CRITICAL RULE: If amount_ambiguity_flag is True,
    # amount_min, amount_max, and amount_typical MUST all be None.
    # Never auto-populate financial fields when the amount is unclear.
    # Examples that trigger ambiguity flag:
    # "50 hazaar", "do lakh", "let's discuss rates", "competitive budget",
    # "as per your rate card", any non-numeric expression

    # Contract signals
    exclusivity_mentioned: bool = False
    exclusivity_scope: Optional[str] = None     # "instagram only", "all platforms", etc.
    exclusivity_duration_days: Optional[int] = None
    payment_terms_mentioned: Optional[str] = None  # "NET-30", "50% upfront", etc.
    payment_days: Optional[int] = None
    deliverables: List[str] = []                # ["1 Reel", "3 Stories", "1 YouTube integration"]
    timeline_days: Optional[int] = None         # days to deliver after acceptance

    # Deal status
    deal_status: Literal[
        "unanswered",    # creator never replied
        "negotiating",   # back and forth in progress
        "accepted",      # deal confirmed
        "rejected",      # creator or brand declined
        "delivered",     # content posted
        "invoiced",      # invoice sent
        "paid",          # payment received
        "overdue",       # payment past due
        "cancelled"      # deal fell through
    ] = "unanswered"

    negotiation_state: Optional[Literal[
        "initial_inquiry", "counter_sent", "counter_received",
        "terms_agreed", "contract_sent", "signed"
    ]] = None

    # Sender metadata
    brand_contact_email: Optional[str] = None
    is_agency_contact: bool = False             # True if an agency is reaching out on behalf of brand
    gmail_thread_id: str = ""

    # Response timing
    creator_response_time_hrs: Optional[float] = None   # hours between first email and creator reply
    thread_unanswered: bool = False             # True if creator never replied to this thread

    # Extraction quality
    extraction_confidence: float = 0.0         # 0.0–1.0: model's confidence in this extraction
    requires_human_review: bool = False
    review_reason: Optional[str] = None        # why human review is needed

    # Hindi/mixed language flag
    hindi_mode: bool = False                   # True if email contains Hindi content
    language: str = "en"

    # Email metadata
    sender_email: str = ""
    subject: str = ""
    date_sent: Optional[str] = None            # ISO string from email header


class ContractExtraction(BaseModel):
    """
    Output schema for extracting structured data from a PDF contract attachment.
    Used separately from DealExtraction — runs only on PDF attachments in deal threads.
    """
    payment_days: Optional[int] = None
    payment_structure: Optional[str] = None    # "upfront", "milestone", "net-30", etc.
    exclusivity_scope: Optional[str] = None
    exclusivity_duration_days: Optional[int] = None
    ip_ownership: Optional[Literal["creator_retains", "brand_acquires", "shared", "not_stated"]] = None
    kill_fee_present: bool = False
    kill_fee_percentage: Optional[float] = None
    revision_limit: Optional[int] = None
    usage_rights_duration_days: Optional[int] = None
    content_approval_required: bool = False
    morality_clause_present: bool = False
    overall_risk_score: float = 0.0            # 1.0 (creator-friendly) to 5.0 (brand-heavy)
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    extraction_confidence: float = 0.0
```

---

## PART 3 — THE EXTRACTION WORKER (core of Session 3)

This replaces the stub at `/workers/extract-thread`. Build in `backend/workers/extract_thread.py`.

### 3A — Gemini Extraction Call

```python
# backend/workers/extract_thread.py

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional
from bson import ObjectId

from google import genai
from google.genai import types

from backend.models.deal import DealExtraction
from backend.models.common import DataClassificationTier, AgentActionType, ActionResult
from backend.database.mongodb import get_db_singleton
from backend.services.mongodb_writer import write_with_classification, upsert_with_classification
from backend.services.action_policy import get_action_policy, ActionType

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768

# ── Extraction system prompt ──────────────────────────────────────────────────

DEAL_EXTRACTION_SYSTEM_PROMPT = """
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
    - Voice profile contribution (outbound emails only)
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

        # ── Step 7: Contribute to voice profile (outbound analysis) ──────────
        # Voice profile is extracted from outbound emails — see Part 4

        # ── Step 8: Update job progress ──────────────────────────────────────
        if job_id:
            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$inc": {"threads_extraction_complete": 1},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

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

        logger.info(f"Extraction complete: thread={thread_id} brand={extraction.brand_name} deal_id={deal_id}")

    except Exception as e:
        logger.error(f"Extraction worker error for thread {thread_id}: {e}", exc_info=True)
        if job_id:
            await db.ingestion_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {"$inc": {"threads_errored": 1}, "$set": {"updated_at": datetime.utcnow()}}
            )


async def _run_deal_extraction(
    sanitised_text: str,
    sender_email: str,
    subject: str,
    thread_id: str,
    hindi_mode: bool,
) -> DealExtraction:
    """Calls Gemini Flash with structured output schema."""
    from backend.services.gemini_client import get_gemini_client_genai
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
            max_output_tokens=1500,
        )
    )

    result = DealExtraction.model_validate_json(response.text)
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
    from backend.services.gemini_client import get_gemini_client_genai
    import numpy as np

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
    arr = np.array(vector, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


async def _upsert_brand(db, extraction: DealExtraction) -> Optional[str]:
    """Upserts brand document. Returns brand _id as string."""
    if not extraction.brand_domain and not extraction.brand_name:
        return None

    lookup_key = extraction.brand_domain or extraction.brand_name.lower().replace(" ", "")

    brand_doc = {
        "name": extraction.brand_name or lookup_key,
        "domain": extraction.brand_domain or "",
        "category": extraction.brand_category or "other",
        "updated_at": datetime.utcnow(),
    }

    # Running payment intelligence update (only if we have payment data)
    if extraction.payment_days:
        brand_doc["payment_intelligence.last_seen_payment_days"] = extraction.payment_days

    await db.brands.update_one(
        {"$or": [
            {"domain": extraction.brand_domain} if extraction.brand_domain else {},
            {"name": {"$regex": f"^{extraction.brand_name}$", "$options": "i"}} if extraction.brand_name else {},
        ]},
        {
            "$set": brand_doc,
            "$setOnInsert": {
                "created_at": datetime.utcnow(),
                "payment_intelligence": {
                    "payment_reliability": 0.5,
                    "avg_payment_days": None,
                    "total_deals_on_platform": 0,
                },
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

    brand = await db.brands.find_one({"domain": extraction.brand_domain or ""})
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
        "initiated_at": date_range_start or datetime.utcnow().isoformat(),
        "extraction_confidence": extraction.extraction_confidence,
        "requires_human_review": extraction.requires_human_review,
        "embedding_vector": embedding_vector,
        "embedding_model": f"{EMBEDDING_MODEL}-{EMBEDDING_DIMENSIONS}d",
        "anonymisation_eligible": True,
        "niche_snapshot": None,         # filled by a separate creator lookup
        "follower_tier_snapshot": None, # filled by a separate creator lookup
        "data_classification": {
            "tier": "personal_identifiable",
            "deletion_policy": "on_request_30d",
            "anonymisation_eligible": True,
            "export_eligible": True,
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
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
                    "description": f"Inferred from brand deal history",
                    "updated_at": datetime.utcnow(),
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
                    "created_at": datetime.utcnow(),
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
                    "evidence.last_observed": datetime.utcnow(),
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
            {"$inc": {"threads_low_confidence": 1}, "$set": {"updated_at": datetime.utcnow()}}
        )
```

---

## PART 4 — VOICE PROFILE EXTRACTION

Voice profile runs as a separate pass after initial deal extraction, using only the creator's **outbound** email text (their replies, not the brand's messages). This separation from DealExtraction is intentional — voice is about writing style, not deal signals.

Build in `backend/services/voice_profiler.py`:

```python
# backend/services/voice_profiler.py

import asyncio
import re
import logging
from typing import List, Optional
from datetime import datetime
from google.genai import types

logger = logging.getLogger(__name__)

VOICE_PROFILER_MODEL = "gemini-2.5-flash"

VOICE_EXTRACTION_PROMPT = """
Analyse these email replies written by a content creator and extract their writing style.
These are OUTBOUND emails — the creator's own words, not brands' messages.

Extract ONLY from the provided text. Do not infer what isn't there.

Return JSON:
{
  "avg_sentence_length": float (average words per sentence),
  "formality_score": float (1.0=very casual, 5.0=very formal),
  "formality_label": "very_casual" | "casual" | "neutral" | "professional",
  "emoji_frequency": float (average emojis per message),
  "top_emojis": [list of up to 5 most used emojis],
  "common_openers": [list of up to 3 phrases the creator uses to start emails],
  "common_closers": [list of up to 3 phrases they use to end emails],
  "uses_caps_emphasis": boolean (do they use ALL CAPS for emphasis?),
  "avg_response_length": integer (average word count per reply),
  "hindi_english_ratio": float (0.0=all English, 1.0=all Hindi),
  "sample_count": integer (how many emails were analysed)
}
"""


async def extract_voice_profile_brand(outbound_emails: List[str]) -> Optional[dict]:
    """
    Extracts voice profile from creator's outbound brand deal emails.
    Requires at least 5 outbound emails for a meaningful profile.
    Returns None if insufficient data.
    """
    if len(outbound_emails) < 5:
        logger.info(f"Insufficient outbound emails ({len(outbound_emails)}) for voice profiling. Skipping.")
        return None

    from backend.services.gemini_client import get_gemini_client_genai
    client = get_gemini_client_genai()

    # Combine up to 30 outbound emails for analysis
    combined = "\n\n---EMAIL---\n\n".join(outbound_emails[:30])

    prompt = f"Creator's outbound brand deal email replies:\n\n{combined}"

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=VOICE_PROFILER_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=VOICE_EXTRACTION_PROMPT,
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=500,
            )
        )

        import json
        profile = json.loads(response.text)
        profile["last_calibrated_at"] = datetime.utcnow().isoformat()
        profile["calibration_sample_count"] = min(len(outbound_emails), 30)
        return profile

    except Exception as e:
        logger.error(f"Voice profile extraction error: {e}")
        return None
```

Voice profile is stored in `creators.voice_profile_brand`. It runs once after the initial ingestion completes and is updated monthly. Wire the call in the ingestion orchestrator after all threads are processed:

```python
# At the end of run_full_ingestion(), after all threads are processed:

# Extract outbound emails for voice profiling
# (These are emails WHERE THE CREATOR IS THE SENDER)
# The ingestion pipeline already has access to thread content during processing
# For now: trigger voice profile extraction as a background job after gate_complete
await publish_sse_event(creator_id, {
    "event": "voice_profiling",
    "message": "Learning your communication style...",
})
# This runs async — voice profile not needed for Audit Report, just for Deal Chief drafts
background_tasks.add_task(run_voice_profiling, creator_id=creator_id)
```

---

## PART 5 — 3 MONGODB AGGREGATION PIPELINES

These run AFTER extraction is complete. They power the Audit Report. All three run in MongoDB — not Python. Build in `backend/services/audit_pipelines.py`.

### Pipeline 1: Revenue Leakage (unanswered deals)

```python
# backend/services/audit_pipelines.py

async def pipeline_revenue_leakage(db, creator_id: str) -> dict:
    """
    Finds deals the creator never responded to and estimates the lost revenue.
    Only uses deals where extraction_confidence >= 0.70.
    """
    pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "thread_unanswered": True,
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$group": {
            "_id": "$financials.currency",
            "unanswered_count": {"$sum": 1},
            "estimated_value_min": {"$sum": {"$ifNull": ["$financials.amount_min", 0]}},
            "estimated_value_max": {"$sum": {"$ifNull": ["$financials.amount_max", 0]}},
            "estimated_value_typical": {"$sum": {"$ifNull": ["$financials.amount_inr", 0]}},
            "brands": {"$push": "$raw_signals.brand_contact_email"},
        }},
        {"$project": {
            "unanswered_count": 1,
            "estimated_value_min": 1,
            "estimated_value_max": 1,
            "estimated_value_typical": 1,
            # Only show range if non-zero
            "has_estimates": {"$gt": ["$estimated_value_max", 0]},
        }}
    ]

    results = await db.deals.aggregate(pipeline).to_list(None)
    return {
        "unanswered_deals": results[0].get("unanswered_count", 0) if results else 0,
        "estimated_value_typical": results[0].get("estimated_value_typical", 0) if results else 0,
        "estimated_value_min": results[0].get("estimated_value_min", 0) if results else 0,
        "estimated_value_max": results[0].get("estimated_value_max", 0) if results else 0,
        "has_estimates": results[0].get("has_estimates", False) if results else False,
        # NOTE: If has_estimates=False, show "value unknown — amount not stated in emails"
        # NEVER show a rate we cannot cite. Show deal count instead.
    }


async def pipeline_payment_reliability(db, creator_id: str) -> list:
    """
    Ranks brands by payment reliability based on known deal outcomes.
    Only includes brands with at least 1 deal in a terminal status.
    """
    pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": {"$in": ["paid", "overdue", "invoiced", "delivered"]},
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$lookup": {
            "from": "brands",
            "localField": "brand_id",
            "foreignField": "_id",
            "as": "brand"
        }},
        {"$unwind": {"path": "$brand", "preserveNullAndEmpty": True}},
        {"$group": {
            "_id": "$brand_id",
            "brand_name": {"$first": "$brand.name"},
            "total_deals": {"$sum": 1},
            "paid_count": {"$sum": {"$cond": [{"$eq": ["$status", "paid"]}, 1, 0]}},
            "overdue_count": {"$sum": {"$cond": [{"$eq": ["$status", "overdue"]}, 1, 0]}},
            "avg_payment_days": {"$avg": "$financials.payment_days"},
        }},
        {"$addFields": {
            "payment_reliability": {
                "$cond": [
                    {"$eq": ["$total_deals", 0]},
                    0.5,
                    {"$divide": ["$paid_count", "$total_deals"]}
                ]
            }
        }},
        {"$sort": {"payment_reliability": 1}},  # worst payers first
        {"$limit": 10}
    ]

    return await db.deals.aggregate(pipeline).to_list(None)


async def pipeline_rate_gap(db, creator_id: str) -> dict:
    """
    Compares creator's accepted deal rates against niche_graph benchmarks.
    Only runs if creator has accepted deals with non-ambiguous amounts.
    """
    creator = await db.creators.find_one({"_id": ObjectId(creator_id)})
    if not creator:
        return {}

    niche = creator.get("niche")
    follower_tier = creator.get("follower_tier")
    if not niche or not follower_tier:
        return {}

    # Get creator's actual accepted rates (non-ambiguous only)
    deal_pipeline = [
        {"$match": {
            "creator_id": creator_id,
            "status": {"$in": ["accepted", "paid", "delivered"]},
            "financials.amount_ambiguity_flag": False,
            "financials.amount_inr": {"$gt": 0},
            "extraction_confidence": {"$gte": 0.70},
        }},
        {"$group": {
            "_id": "$deal_type",
            "avg_rate": {"$avg": "$financials.amount_inr"},
            "deal_count": {"$sum": 1},
        }}
    ]

    creator_rates = await db.deals.aggregate(deal_pipeline).to_list(None)

    # Get market benchmarks from niche_graph
    benchmarks = {}
    for rate_entry in creator_rates:
        deal_type = rate_entry.get("_id")
        if not deal_type:
            continue

        benchmark = await db.niche_graph.find_one({
            "niche": niche,
            "follower_tier": follower_tier,
            "content_format": deal_type,
            "confidence_weight": {"$gte": 0.40},
        })

        if benchmark and benchmark.get("rate_p50") and rate_entry.get("avg_rate"):
            gap_pct = round(
                (rate_entry["avg_rate"] - benchmark["rate_p50"]) / benchmark["rate_p50"] * 100, 1
            )
            benchmarks[deal_type] = {
                "creator_avg": round(rate_entry["avg_rate"], 0),
                "market_p50": benchmark["rate_p50"],
                "gap_percentage": gap_pct,
                "gap_label": "below_market" if gap_pct < -10 else ("above_market" if gap_pct > 10 else "at_market"),
                "deal_count": rate_entry["deal_count"],
                "benchmark_confidence": benchmark.get("confidence_weight", 0.40),
                # If benchmark_confidence < 0.55: show transparency note
            }

    return benchmarks
```

---

## PART 6 — AUDIT REPORT GENERATION

### 6A — Synthesis Context (typed, passed to Gemini Pro)

```python
# backend/models/audit.py

from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class SynthesisContext(BaseModel):
    """Typed context passed to Gemini Pro for Audit Report synthesis."""
    creator_id: str
    creator_niche: str
    creator_follower_tier: str
    creator_handle: Optional[str]

    # From Pipeline 1
    unanswered_deal_count: int
    unanswered_value_typical: float
    unanswered_value_min: float
    unanswered_value_max: float
    has_financial_estimates: bool

    # From Pipeline 2
    payment_reliability_data: List[Dict]

    # From Pipeline 3
    rate_gap_data: Dict

    # Totals
    total_deals_found: int
    total_deals_extracted: int
    total_confidence_below_threshold: int  # went to HITL

    # Skills Map signals
    confirmed_preferences: List[Dict]      # preferences with confidence > 0.7


class AuditFinding(BaseModel):
    """A single finding in the Audit Report."""
    section: str           # "revenue_leakage" | "payment_risk" | "rate_gap" | "operational_dna"
    title: str
    severity: str          # "high" | "medium" | "low" | "positive"
    finding_text: str      # what was found — plain language
    evidence: str          # what data supports this — cite specific numbers or counts
    recommendation: str    # what the creator should do about it
    value_inr: Optional[float] = None   # monetary value if applicable — None if unknown
    value_unknown: bool = False         # True if finding has monetary impact but amount unclear
    # RULE: If value is unknown, say "Unknown — amount not stated in emails"
    # NEVER fabricate a rupee amount. Never use "approximately" without a cited basis.

class SynthesisReport(BaseModel):
    """Output from Gemini Pro synthesis."""
    findings: List[AuditFinding]
    executive_summary: str              # 2–3 sentences, plain language
    total_recoverable_value: Optional[float]   # None if no non-ambiguous amounts
    total_recoverable_unknown: bool            # True if there are unanswered deals with unknown value
    skills_map_summary: str            # what ThreadComb learned about how this creator operates
    data_quality_note: Optional[str]   # honest note if data was limited or confidence was low
```

### 6B — Gemini Pro Synthesis Call

```python
# backend/services/audit_generator.py

import asyncio
import logging
from datetime import datetime
from backend.models.audit import SynthesisContext, SynthesisReport, AuditFinding

logger = logging.getLogger(__name__)
SYNTHESIS_MODEL = "gemini-2.5-pro"

SYNTHESIS_SYSTEM_PROMPT = """
You are generating a Skills Audit Report for a content creator in India.
This report tells them exactly what their brand deal operations look like
and what they are leaving on the table.

CRITICAL RULES — NO EXCEPTIONS:

1. NEVER fabricate rupee amounts. If the data shows value_unknown=true,
   say "Value unknown — amount not stated in emails" in that finding.
   A finding with zero financial data is still valuable — state what you know (deal count, brand name).

2. NEVER use "approximately" or "estimated" unless you can cite the basis.
   If extraction_confidence is low, acknowledge it: "Based on limited data..."

3. EVERY finding must have evidence — specific numbers, counts, or deal references.
   "The creator left money on the table" is not a finding.
   "The creator did not reply to 3 brand deal emails. The brands: Minimalist, Mamaearth, and a third brand whose amount was not stated." is a finding.

4. Tone: Direct, honest, supportive. Not alarming. Not salesy.
   The creator is smart — treat them that way.

5. Data quality note: If fewer than 5 deals were extracted with high confidence,
   include a data_quality_note saying "This audit is based on limited data.
   Results will improve as more of your email history is analysed."

Return valid JSON matching the SynthesisReport schema. No markdown. JSON only.
"""


async def generate_audit_report(context: SynthesisContext) -> SynthesisReport:
    """Calls Gemini Pro to synthesise the audit findings."""
    from backend.services.gemini_client import get_gemini_client_genai
    from google.genai import types
    client = get_gemini_client_genai()

    # Serialize context — Gemini reads this as grounding data
    context_json = context.model_dump_json(indent=2)

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=SYNTHESIS_MODEL,
        contents=f"Generate the Audit Report for this creator's data:\n\n{context_json}",
        config=types.GenerateContentConfig(
            system_instruction=SYNTHESIS_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=SynthesisReport,
            temperature=0.1,
            max_output_tokens=3000,
        )
    )

    report = SynthesisReport.model_validate_json(response.text)
    return report
```

### 6C — PDF Generation

```python
# backend/services/pdf_generator.py
# Uses reportlab to generate the Audit Report PDF.
# Saves to Google Cloud Storage and returns the GCS URL.

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
import io
from datetime import datetime
from backend.models.audit import SynthesisReport


def generate_audit_pdf(report: SynthesisReport, creator_handle: str, creator_niche: str) -> bytes:
    """Generates the Audit Report PDF. Returns PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"ThreadComb Skills Audit", styles["Title"]))
    story.append(Paragraph(f"{creator_handle} · {creator_niche.title()} · {datetime.utcnow().strftime('%B %Y')}", styles["Normal"]))
    story.append(Spacer(1, 10*mm))

    # Executive Summary
    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(Paragraph(report.executive_summary, styles["Normal"]))
    story.append(Spacer(1, 6*mm))

    # Total recoverable value
    if report.total_recoverable_value:
        story.append(Paragraph(
            f"Identified recoverable value: ₹{report.total_recoverable_value:,.0f}",
            styles["Heading3"]
        ))
    elif report.total_recoverable_unknown:
        story.append(Paragraph(
            "Recoverable value: Unknown (deal amounts not stated in emails — deal count tracked below)",
            styles["Normal"]
        ))
    story.append(Spacer(1, 8*mm))

    # Findings
    story.append(Paragraph("Findings", styles["Heading2"]))

    severity_colours = {
        "high": colors.HexColor("#A32D2D"),
        "medium": colors.HexColor("#BA7517"),
        "low": colors.HexColor("#378ADD"),
        "positive": colors.HexColor("#1D9E75"),
    }

    for finding in report.findings:
        colour = severity_colours.get(finding.severity, colors.black)
        story.append(Paragraph(finding.title, styles["Heading3"]))
        story.append(Paragraph(finding.finding_text, styles["Normal"]))
        if finding.value_inr:
            story.append(Paragraph(f"Value: ₹{finding.value_inr:,.0f}", styles["Normal"]))
        elif finding.value_unknown:
            story.append(Paragraph("Value: Amount not stated in emails", styles["Normal"]))
        story.append(Paragraph(f"Evidence: {finding.evidence}", styles["Italic"]))
        story.append(Paragraph(f"Recommendation: {finding.recommendation}", styles["Normal"]))
        story.append(Spacer(1, 5*mm))

    # Data quality note
    if report.data_quality_note:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph("Note on Data Quality", styles["Heading3"]))
        story.append(Paragraph(report.data_quality_note, styles["Normal"]))

    # Footer
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("Generated by ThreadComb · threadcomb.com · All data is derived from your own Gmail account.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


async def upload_audit_pdf_to_gcs(pdf_bytes: bytes, creator_id: str) -> str:
    """Uploads PDF to GCS and returns the public URL."""
    from google.cloud import storage
    import asyncio
    from backend.config import settings

    def _upload():
        client = storage.Client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob_name = f"audit_reports/{creator_id}/{datetime.utcnow().strftime('%Y%m')}_audit.pdf"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")
        blob.make_public()
        return blob.public_url

    return await asyncio.to_thread(_upload)
```

---

## PART 7 — AUDIT REPORT ORCHESTRATOR

Wire everything together. Build in `backend/routers/audit.py`.

```python
# backend/routers/audit.py

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from bson import ObjectId
from datetime import datetime

router = APIRouter()


@router.post("/audit/generate/{creator_id}")
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
    if str(current_creator["_id"]) != creator_id:
        raise HTTPException(status_code=403)

    background_tasks.add_task(run_audit_generation, creator_id=creator_id)
    return {"status": "generating", "message": "Your audit report is being prepared."}


@router.get("/audit/report/{creator_id}")
async def get_audit_report(
    creator_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """Returns the latest audit report for a creator."""
    if str(current_creator["_id"]) != creator_id:
        raise HTTPException(status_code=403)

    db = get_db_singleton()
    report = await db.audit_reports.find_one(
        {"creator_id": creator_id},
        sort=[("created_at", -1)]
    )
    if not report:
        raise HTTPException(status_code=404, detail="No audit report yet")

    report["_id"] = str(report["_id"])
    return report


async def run_audit_generation(creator_id: str):
    """Full audit generation pipeline — runs in background."""
    from backend.services.audit_pipelines import pipeline_revenue_leakage, pipeline_payment_reliability, pipeline_rate_gap
    from backend.services.audit_generator import generate_audit_report
    from backend.services.pdf_generator import generate_audit_pdf, upload_audit_pdf_to_gcs
    from backend.models.audit import SynthesisContext

    db = get_db_singleton()
    creator = await db.creators.find_one({"_id": ObjectId(creator_id)})
    if not creator:
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

    # Generate PDF
    pdf_bytes = generate_audit_pdf(
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
        "created_at": datetime.utcnow(),
        "data_classification": {
            "tier": "personal_identifiable",
            "deletion_policy": "on_request_30d",
            "export_eligible": True,
        }
    }
    await db.audit_reports.insert_one(report_doc)

    # Create audit_reports collection if needed (add to create_indexes())

    # Notify creator via SSE
    from backend.services.sse_manager import publish_sse_event
    await publish_sse_event(creator_id, {
        "event": "audit_complete",
        "message": "Your Skills Audit is ready.",
        "pdf_url": pdf_url,
    })
```

---

## PART 8 — FIRST SIGNAL MODULE

This is the most important UX addition in Session 3. It gives creators immediate value within 60 seconds of connecting Gmail — before the full audit runs.

### What it does:
After the gate classification pass completes (threads identified as deal signals), but BEFORE Gemini extraction runs, surface one meaningful signal to the creator immediately.

```python
# In run_full_ingestion(), right after gate_complete SSE event:

async def generate_first_signal(creator_id: str, thread_statuses: list):
    """
    Generates immediate value for the creator within 60 seconds of audit start.
    Uses gate classification results only — no Gemini extraction yet.
    Runs BEFORE the extraction worker processes threads.
    """
    from backend.services.sse_manager import publish_sse_event

    deal_signal_threads = [
        t for t in thread_statuses
        if t.get("gate_decision") in ("deal_signal", "hindi_mixed")
    ]
    unanswered_count = len(deal_signal_threads)

    if unanswered_count == 0:
        return  # No deal signals found — don't show a first signal

    # Pull sender emails from thread statuses for display
    # These are already available from the gate pass
    brand_emails = list(set(
        t.get("sender_email", "").split("@")[-1]
        for t in deal_signal_threads
        if t.get("sender_email")
    ))[:3]

    brand_domains_display = ", ".join(brand_emails) if brand_emails else "several brands"

    await publish_sse_event(creator_id, {
        "event": "first_signal",
        "title": "First finding — before your full audit runs",
        "message": f"We found {unanswered_count} brand deal {'email' if unanswered_count == 1 else 'emails'} in your inbox.",
        "detail": f"Brands involved: {brand_domains_display}",
        "sub_detail": "We're now extracting the details from each one. Your full audit will be ready soon.",
        "deal_count": unanswered_count,
    })
```

### Frontend: First Signal Card (React 19, Next.js 15 App Router)

Build in `frontend/app/dashboard/components/FirstSignalCard.tsx`:

```tsx
// frontend/app/dashboard/components/FirstSignalCard.tsx
// React 19 component — shows when first_signal SSE event arrives

'use client'

interface FirstSignalData {
  title: string
  message: string
  detail: string
  sub_detail: string
  deal_count: number
}

interface FirstSignalCardProps {
  signal: FirstSignalData | null
}

export function FirstSignalCard({ signal }: FirstSignalCardProps) {
  if (!signal) return null

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900 p-5 mb-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-white text-sm font-bold">{signal.deal_count}</span>
        </div>
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-1">
            First finding
          </p>
          <p className="text-sm font-medium text-foreground mb-1">{signal.message}</p>
          <p className="text-sm text-muted-foreground mb-0.5">{signal.detail}</p>
          <p className="text-xs text-muted-foreground">{signal.sub_detail}</p>
        </div>
      </div>
    </div>
  )
}
```

### Dashboard update — four states with First Signal

Update `frontend/app/dashboard/page.tsx` to handle:
1. **No Gmail connected** → empty state with Connect Gmail CTA
2. **Gmail connected, audit not started** → "Start Your Audit" button enabled
3. **Audit running** → `<IngestionProgress />` + `<FirstSignalCard />` when signal arrives
4. **Audit complete** → Full dashboard with deal pipeline, findings summary, PDF download

---

## PART 9 — LOYALTY SIGNALS (minimal, from what we have)

Without Instagram/YouTube API access yet, loyalty signals come from Gmail only. This is a thin layer that gives creators something meaningful on the dashboard immediately — not the full fan management system.

### What to extract from Gmail during the ingestion pass:

In the gate classifier, add a new gate decision type: `FAN_SIGNAL`. Fan emails are not brand deals but are valuable data. Add this to the gate pass (small addition — no new model call needed):

```python
# Additional signals from Gmail gate pass (add to ingestion_gate.py):

# Fan signal keywords (check AFTER brand deal gate — only classify fan signals
# for threads that did not pass as deal signals)
FAN_SIGNAL_KEYWORDS = [
    "love your content", "huge fan", "inspired by", "your video helped",
    "could you do a video on", "tutorial request", "collaboration between creators",
    "your work is amazing", "can you review", "you should cover",
]

# In the gate function, after the deal signal check:
# If is_deal_signal=False and not spam → check for fan signal
# If fan signal detected → create a lightweight fan_signal document (NOT fan_interaction yet)
```

### A new lightweight collection: `fan_signals`

This is a simplified version of fan_interactions — built from Gmail data, not Instagram API. Schema:

```python
class FanSignalFromGmail(BaseModel):
    creator_id: str
    signal_type: str          # "fan_appreciation" | "content_request" | "creator_collab" | "general"
    sender_email: str         # hashed for privacy — store SHA-256 only
    subject_preview: str      # first 60 chars of subject only
    detected_at: datetime
    source: str = "gmail"
    data_classification: dict = Field(default_factory=lambda: {
        "tier": "personal_identifiable",
        "deletion_policy": "on_request_30d",
    })
```

On the dashboard, surface this as:
> "ThreadComb detected 23 fan engagement emails in your inbox alongside your brand deals. Fan management launches in the next version."

This teases Phase 2, creates anticipation, and shows the creator that ThreadComb sees more than just brand deals.

---

## PART 10 — NEW COLLECTION: audit_reports

Add to `backend/database/mongodb.py` create_indexes():

```python
# audit_reports collection
await db.audit_reports.create_index("creator_id")
await db.audit_reports.create_index([("creator_id", 1), ("created_at", -1)])

# fan_signals collection
await db.fan_signals.create_index("creator_id")
await db.fan_signals.create_index("detected_at")
```

---

## PART 11 — WIRE THE DASHBOARD "Start Your Audit" BUTTON

The button is currently disabled in the empty state. Enable it when `creator.gmail_connected === true`.

On click:
1. POST `/ingestion/start` → returns `{job_id, sse_channel}`
2. Store `job_id` in component state
3. Open SSE connection to `/sse/ingestion/{creator_id}`
4. Show `<IngestionProgress />` component
5. Listen for `first_signal` event → show `<FirstSignalCard />`
6. Listen for `audit_complete` event → navigate to `/dashboard/audit`

Build `frontend/app/dashboard/audit/page.tsx`:
- Shows the executive summary from the audit report
- Shows each finding as a card (severity-coloured)
- Shows the PDF download button
- Shows the Skills Map summary section ("Here's what we learned about how you work")

---

## PART 12 — DEPENDENCIES TO ADD

```
# Add to backend/requirements.txt
numpy>=1.26.0       # for embedding normalization
reportlab>=4.2.0    # for PDF generation
google-cloud-storage>=2.16.0  # for GCS upload
```

---

## EXIT CRITERIA — ALL MUST PASS BEFORE SESSION 4

1. **Dev trigger works:** POST `/workers/trigger-direct` with a valid sanitised thread payload → extraction runs → deals document appears in MongoDB Atlas.

2. **DealExtraction schema:** Import `DealExtraction` and `ContractExtraction` from `backend.models.deal` without error. Instantiate both with minimal required fields.

3. **Amount ambiguity enforced:** Run extraction on a thread containing "let's discuss rates." Confirm `amount_ambiguity_flag: True` and `amount_typical: None` in the resulting MongoDB document.

4. **Embedding normalization:** Generate an embedding, check that the L2 norm of the stored vector equals 1.0 (within floating point tolerance: `abs(np.linalg.norm(vector) - 1.0) < 0.001`).

5. **Atlas Vector Search reachable:** With at least one deal in MongoDB that has an embedding_vector, run a $vectorSearch aggregation via pymongo. Confirm it returns results (even if just 1 document returning itself).

6. **Brand upserted:** After extraction, confirm a brands document exists for the extracted brand_domain. Confirm `payment_intelligence.total_deals_on_platform >= 1`.

7. **Skills Map updated:** For a deal with status "accepted", confirm a skills_map preference node exists for that brand category with `evidence.count >= 1`.

8. **Audit Report runs:** With at least 3 deals in MongoDB for a test creator, call `run_audit_generation(creator_id)`. Confirm an audit_reports document is created. Confirm `pdf_url` is a non-empty string. Confirm `data_quality_note` is populated (since 3 deals is a small sample).

9. **First Signal fires:** Run ingestion on a Gmail account with at least one brand deal email. Confirm the SSE stream emits a `first_signal` event with `deal_count > 0` before the audit_complete event.

10. **Dashboard button enabled:** Log in, complete onboarding, connect Gmail. Confirm "Start Your Audit" button is enabled. Click it. Confirm ingestion starts and progress appears in the UI.

11. **No fabricated amounts:** Inspect all audit_reports documents. Confirm no finding has `value_inr > 0` where the source deals all have `amount_ambiguity_flag: True`.

12. **Audit PDF opens:** Download the generated PDF. Confirm it opens correctly, shows the creator handle, niche, and at least one finding section.

---

## NOTES FOR COPILOT AGENT

- `get_gemini_client_genai()` should return a `google.genai.Client` initialized with `GEMINI_API_KEY`. This is separate from the old `LlmChat` singleton — build a new function in `backend/services/gemini_client.py` that returns the genai.Client.
- numpy is needed only for embedding normalization. If numpy causes dependency conflicts, the normalization can be done in pure Python: `norm = sum(x**2 for x in vector)**0.5; normalized = [x/norm for x in vector]`.
- The `audit_reports` collection is new — add it to the `create_indexes()` function and to any collection-existence checks in `run_seed.py`.
- All datetime values use `datetime.utcnow()` not `datetime.now()`.
- `reportlab` generates PDFs synchronously. Wrap the `generate_audit_pdf()` call in `asyncio.to_thread()` if called from an async context.
- The First Signal module runs on gate results only — it does not need any extraction to complete first. Timing: fire it immediately after the gate pass finishes, while extraction tasks are still queued.
- For the dev direct trigger: the Cloud Tasks payload format is identical to the `/workers/extract-thread` body. The `/workers/trigger-direct` endpoint accepts the same JSON.
- `fan_signals` stores only the SHA-256 hash of the sender email — never the raw email address. This is a DPDP compliance decision for third-party fan data.

---

*ThreadComb Session 3 — DNA Reader complete. First Signal active. Immediate creator value delivered.*
*The audit exists. The conversation with the creator begins.*
