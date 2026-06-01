# THREADCOMB — SESSION 4 PROMPT
# Deal Chief Agent — The most user-visible agent in ThreadComb
# Next.js 15 + React 19 App Router, FastAPI, MongoDB Atlas, Google ADK
# Paste this entire document to Copilot Agent as context. Work section by section.

---

## IDENTITY ANCHOR

**Product:** ThreadComb — AI-powered creator operations platform.
**Stack:** Next.js 15 + React 19 (App Router, TypeScript) + FastAPI (Python 3.11, Pydantic v2, motor) + MongoDB Atlas M0 + Google ADK + Gemini API.

**What exists from Sessions 1–3:**
- MongoDB: all collections live. deals has real documents with 768d normalised embedding_vector. brands upserted with payment_intelligence. skills_map has preference nodes. atlas Vector Search index `deal_embeddings_index` on deals (768d cosine) is READY.
- FastAPI: Gmail ingestion pipeline complete. DNA Reader extraction worker complete. Audit Report generation complete. `/workers/trigger-direct` dev endpoint live.
- All 7 Session 3 verification tests pass with real data including Atlas Vector Search self-match = 1.0000 and financial accuracy (₹75,000 exact, no hallucination).
- React: Dashboard has 4 states (no_gmail → ready → running → complete). Audit page shows findings + PDF download.

**Session 4 builds:** The Deal Chief agent — the agent that watches for new inbound brand deal emails, queries the Skills Map for context, generates a reply draft in the creator's voice, and routes it for one-tap creator approval before sending.

**Does NOT build:** Revenue Guardian (Session 5), Fan Manager (Phase 2), full Google ADK orchestrator (Session 5).

---

## WHAT THE DEAL CHIEF DOES — THE 8-STEP PIPELINE

When a new brand deal email arrives in the creator's Gmail:

1. **Brand history lookup** — query MongoDB brands collection for this sender's domain
2. **Atlas Vector Search** — find the 5 most similar historical deals from this creator (using RETRIEVAL_QUERY task type — different from the RETRIEVAL_DOCUMENT used during indexing)
3. **Skills Map preference query** — fetch confirmed PREFER/AVOID nodes with confidence ≥ 0.70
4. **Rate benchmark** — query niche_graph for P25/P50/P75 for creator's niche + tier + detected deal type
5. **Complexity scoring** — decide Gemini Flash vs Pro based on contract complexity signals
6. **Draft generation (Call A)** — Gemini with voice_profile_brand context + all 4 layers of MongoDB context
7. **Voice compliance check (Call B)** — separate Gemini call evaluates the draft against the voice profile. Does NOT know it is evaluating Call A output. Returns voice_compliance_score.
8. **HITL presentation** — push draft + context to creator UI via SSE. Creator: Approve & Send / Edit / Reject / Revise. On Approve: Gmail send → MongoDB deal insert/update → Calendar event → agent_actions log.

---

## PART 1 — NEW FILES TO CREATE

```
backend/
├── services/
│   ├── deal_chief.py           # Core 8-step pipeline
│   ├── voice_compliance.py     # Two-model evaluator (Call B — separate from generator)
│   └── deal_search.py          # Atlas Vector Search query for similar deals
├── models/
│   └── draft.py                # DraftResult, DraftFlag, VoiceComplianceResult schemas
├── routers/
│   └── deals.py                # /deals/inbound, /deals/draft/{deal_id}, /deals/approve/{deal_id}

frontend/src/app/
├── dashboard/
│   ├── deals/
│   │   └── page.tsx            # Deal inbox — all inbound deals with drafts
│   └── components/
│       ├── DealCard.tsx        # Single deal card with draft + approval buttons
│       ├── FlagsPanel.tsx      # Flags: exclusivity, rate gap, brand score
│       ├── BrandScoreBar.tsx   # Visual brand payment reliability indicator
│       └── ShadowDraftModal.tsx # Full draft editor + context panel
```

---

## PART 2 — PYDANTIC SCHEMAS

Build in `backend/models/draft.py`:

```python
# backend/models/draft.py

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class DraftFlag(BaseModel):
    """A single flag raised during draft generation context analysis."""
    flag_type: Literal[
        "exclusivity_too_long",      # exclusivity duration > creator's standard
        "rate_below_market",         # offered rate < niche P50 by more than 15%
        "missing_kill_fee",          # no kill fee clause mentioned
        "payment_terms_unfavourable",# NET-60 when creator's standard is NET-30
        "brand_slow_payer",          # brand's avg_payment_days > 45
        "brand_overdue_history",     # brand has past overdue invoices
        "ip_rights_broad",           # IP ownership terms seem broad
        "first_time_brand",          # no prior history with this brand
        "agency_contact",            # PR agency contacting on behalf of brand
        "amount_ambiguous",          # deal amount not clearly stated
    ]
    severity: Literal["high", "medium", "low"]
    message: str                    # human-readable explanation for the creator
    recommended_action: Optional[str] = None  # what to do about this flag


class VoiceComplianceResult(BaseModel):
    """
    Output of Call B — the separate voice compliance evaluator.
    This model evaluates the draft from Call A without knowing it generated it.
    """
    voice_compliance_score: float   # 0.0–1.0. Below 0.75: regenerate or warn.
    formality_match: bool           # does formality level match voice_profile_brand?
    emoji_match: bool               # does emoji usage match profile?
    length_match: bool              # is response length appropriate to profile?
    hindi_integration_correct: bool # if creator code-switches, does draft match?
    specific_issues: List[str]      # list of specific voice mismatches found
    overall_assessment: str         # one sentence: why this score


class DraftResult(BaseModel):
    """Complete output of the Deal Chief pipeline for one inbound deal."""
    deal_id: Optional[str] = None   # MongoDB deal _id (set after deal document created)
    thread_id: str
    creator_id: str
    brand_name: Optional[str]
    brand_domain: Optional[str]
    brand_reliability_score: float  # 0.0–1.0 from brands.payment_intelligence
    brand_is_new: bool              # no prior deals with this brand

    # Rate context
    offered_amount: Optional[float] = None
    offered_amount_ambiguous: bool = False
    market_p50: Optional[float] = None
    market_p25: Optional[float] = None
    market_p75: Optional[float] = None
    rate_gap_percentage: Optional[float] = None  # negative = below market
    benchmark_confidence: float = 0.0

    # Similar deals context
    similar_deals_found: int = 0
    similar_deals_summary: Optional[str] = None  # "You've done 3 similar deals at ₹45K–₹65K"

    # The draft
    draft_text: str
    draft_language: str = "en"      # "en" | "hi" | "hi-en"
    model_used: str                  # "gemini-2.5-flash" or "gemini-2.5-pro"
    voice_compliance_score: float
    voice_compliance_issues: List[str] = []

    # Flags
    flags: List[DraftFlag] = []
    has_high_severity_flags: bool = False

    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_latency_ms: Optional[int] = None

    # Creator action
    creator_action: Optional[Literal["approved", "edited", "rejected", "revised"]] = None
    final_text: Optional[str] = None        # set when creator edits or approves
    sent_at: Optional[datetime] = None
    calendar_event_id: Optional[str] = None
```

---

## PART 3 — ATLAS VECTOR SEARCH FOR SIMILAR DEALS

Build in `backend/services/deal_search.py`:

```python
# backend/services/deal_search.py

import asyncio
import logging
import numpy as np
from typing import List, Optional
from google.genai import types

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768


async def embed_for_search(text: str) -> List[float]:
    """
    Generates a normalized embedding for SEARCH (query-side).
    CRITICAL: use task_type="RETRIEVAL_QUERY" — different from RETRIEVAL_DOCUMENT used during indexing.
    This asymmetric task typing is intentional and improves retrieval accuracy.
    """
    from backend.services.gemini_client import get_gemini_client_genai
    client = get_gemini_client_genai()

    if not text.strip():
        return [0.0] * EMBEDDING_DIMENSIONS

    response = await asyncio.to_thread(
        client.models.embed_content,
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",       # ← query side, not RETRIEVAL_DOCUMENT
            output_dimensionality=EMBEDDING_DIMENSIONS,
        )
    )

    vector = response.embeddings[0].values

    # Normalize — required for 768d (not pre-normalized by API)
    arr = np.array(vector, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


async def find_similar_deals(
    db,
    creator_id: str,
    query_text: str,
    num_results: int = 5,
) -> List[dict]:
    """
    Finds the creator's most similar historical deals using Atlas Vector Search.
    Only searches deals with extraction_confidence >= 0.70.
    Returns empty list gracefully if no deals exist yet.
    """
    query_vector = await embed_for_search(query_text)

    pipeline = [
        {
            "$vectorSearch": {
                "index": "deal_embeddings_index",
                "path": "embedding_vector",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": num_results,
                "filter": {
                    "creator_id": {"$eq": creator_id},
                    "extraction_confidence": {"$gte": 0.70},
                    # Only return deals with known outcomes for useful context
                    "status": {"$in": ["accepted", "paid", "delivered", "negotiating"]},
                }
            }
        },
        {
            "$project": {
                "embedding_vector": 0,     # exclude the vector from results
                "score": {"$meta": "vectorSearchScore"},
                "deal_type": 1,
                "status": 1,
                "financials.amount_inr": 1,
                "financials.amount_ambiguity_flag": 1,
                "raw_signals.deliverables": 1,
                "raw_signals.exclusivity_mentioned": 1,
                "raw_signals.payment_terms_mentioned": 1,
                "brand_id": 1,
            }
        }
    ]

    try:
        results = await db.deals.aggregate(pipeline).to_list(num_results)
        return results
    except Exception as e:
        logger.warning(f"Atlas Vector Search error (returning empty): {e}")
        return []


def summarise_similar_deals(similar_deals: List[dict]) -> Optional[str]:
    """
    Produces a one-sentence summary of similar deals for context injection.
    Only includes non-ambiguous amounts. Returns None if no useful data.
    """
    if not similar_deals:
        return None

    amounts = [
        d["financials"]["amount_inr"]
        for d in similar_deals
        if not d.get("financials", {}).get("amount_ambiguity_flag")
        and d.get("financials", {}).get("amount_inr")
    ]

    count = len(similar_deals)
    if amounts:
        avg = sum(amounts) / len(amounts)
        min_a, max_a = min(amounts), max(amounts)
        return f"You've done {count} similar deal{'s' if count > 1 else ''} ranging from ₹{min_a:,.0f} to ₹{max_a:,.0f} (avg ₹{avg:,.0f})."
    else:
        return f"You've done {count} similar deal{'s' if count > 1 else ''} (amounts not on record)."
```

---

## PART 4 — VOICE COMPLIANCE EVALUATOR

Build in `backend/services/voice_compliance.py`:

```python
# backend/services/voice_compliance.py
"""
Call B — the separate voice compliance evaluator.
This function evaluates a draft without knowing it was generated by the Deal Chief.
It does NOT receive any context about what the draft is supposed to say.
It ONLY evaluates: does this draft sound like the creator's voice profile?
"""

import asyncio
import json
import logging
from backend.models.draft import VoiceComplianceResult

logger = logging.getLogger(__name__)
EVALUATOR_MODEL = "gemini-2.5-flash"  # intentionally same model — different prompt, different session

VOICE_EVALUATOR_SYSTEM_PROMPT = """
You are evaluating whether an email draft matches a specific person's writing style.
You are NOT evaluating whether the content is correct, appropriate, or complete.
You are ONLY evaluating style: does this draft sound like someone with this voice profile?

Voice profile fields:
- formality_score: 1.0 (very casual) to 5.0 (very formal)
- emoji_frequency: average emojis per message
- avg_response_length: typical word count
- hindi_english_ratio: 0.0 = all English, 1.0 = all Hindi
- common_openers: phrases this person uses to start messages
- common_closers: phrases this person uses to end messages
- uses_caps_emphasis: does this person use ALL CAPS for emphasis?

Return JSON matching VoiceComplianceResult. Be specific about issues.
Score 1.0 = perfect match. Score below 0.75 = significant mismatch.
"""


async def evaluate_voice_compliance(
    draft_text: str,
    voice_profile: dict,
) -> VoiceComplianceResult:
    """
    Call B — evaluates draft against voice profile.
    Called separately from the draft generation (Call A).
    Never raises — returns a neutral score on any error.
    """
    from backend.services.gemini_client import get_gemini_client_genai
    from google.genai import types
    client = get_gemini_client_genai()

    evaluation_input = f"""
Voice profile to evaluate against:
{json.dumps(voice_profile, indent=2)}

Email draft to evaluate:
{draft_text}

Evaluate whether the draft matches this voice profile.
"""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=EVALUATOR_MODEL,
            contents=evaluation_input,
            config=types.GenerateContentConfig(
                system_instruction=VOICE_EVALUATOR_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=VoiceComplianceResult,
                temperature=0.0,
                max_output_tokens=400,
            )
        )
        return VoiceComplianceResult.model_validate_json(response.text)

    except Exception as e:
        logger.error(f"Voice compliance evaluation error: {e}")
        return VoiceComplianceResult(
            voice_compliance_score=0.5,
            formality_match=True,
            emoji_match=True,
            length_match=True,
            hindi_integration_correct=True,
            specific_issues=[f"Evaluation unavailable: {str(e)[:80]}"],
            overall_assessment="Could not evaluate — using draft as generated."
        )
```

---

## PART 5 — THE DEAL CHIEF CORE PIPELINE

Build in `backend/services/deal_chief.py`:

```python
# backend/services/deal_chief.py

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from google.genai import types

from backend.models.draft import DraftResult, DraftFlag, VoiceComplianceResult
from backend.services.deal_search import find_similar_deals, summarise_similar_deals
from backend.services.voice_compliance import evaluate_voice_compliance

logger = logging.getLogger(__name__)

DRAFT_MODEL_FLASH = "gemini-2.5-flash"
DRAFT_MODEL_PRO = "gemini-2.5-pro"

# Signals that trigger Pro instead of Flash for draft generation
COMPLEXITY_SIGNALS = [
    "equity", "shares", "ownership stake",
    "multi-year", "2 year", "3 year", "annual contract",
    "buyout", "exclusive rights", "all rights", "perpetual",
    "franchise", "white label", "license in perpetuity",
]

DRAFT_SYSTEM_PROMPT = """
You are drafting a reply to a brand deal email on behalf of a content creator in India.

Your job: Write a professional, warm reply that sounds EXACTLY like the creator based on their voice profile.

CRITICAL RULES:
1. VOICE: Match the creator's voice profile exactly.
   - If formality_score is below 2.5 (casual): use casual language, contractions, maybe emojis.
   - If hindi_english_ratio > 0.3: naturally integrate Hindi phrases as this creator would.
   - Match their typical response length (avg_response_length words).
   - Use one of their common_openers to start.
   - Use one of their common_closers to end.

2. NEGOTIATION: Address the context provided.
   - If rate_gap_percentage < -15: suggest a rate closer to market. Phrase it naturally — not "market data says", just "my rate for this type of content is typically ₹X."
   - If exclusivity_concern is flagged: propose a shorter duration. Phrase it as preference, not complaint.
   - If brand is first-time contact: keep tone warm but professional.

3. WHAT TO INCLUDE:
   - Express genuine interest (if creator works in this niche — check preferences)
   - Acknowledge the deliverables mentioned
   - If rate was stated and below market: naturally counter-propose
   - If exclusivity was mentioned: address the duration
   - Ask for the contract or next steps
   - Do NOT mention ThreadComb, AI, or that this is a draft

4. WHAT TO AVOID:
   - Do not fabricate deliverables or rates not in the context
   - Do not make commitments the creator hasn't approved
   - Do not include placeholder text like [NAME] or [DATE]
   - Do not be sycophantic about the brand

Return ONLY the email text. No subject line. No metadata. Just the email body.
"""


async def run_deal_chief_pipeline(
    db,
    creator_id: str,
    thread_id: str,
    sanitised_thread_text: str,
    sender_email: str,
    subject: str,
    extraction,        # DealExtraction result from the ingestion pipeline
) -> DraftResult:
    """
    Runs the full 8-step Deal Chief pipeline for one inbound brand deal email.
    Returns a DraftResult — the complete context and draft for creator review.
    """
    start_time = time.time()

    # ── Fetch creator for context ─────────────────────────────────────────────
    creator = await db.creators.find_one({"_id": ObjectId(creator_id)})
    if not creator:
        raise ValueError(f"Creator {creator_id} not found")

    voice_profile = creator.get("voice_profile_brand", {})
    niche = creator.get("niche")
    follower_tier = creator.get("follower_tier")

    # ── Step 1: Brand history lookup ──────────────────────────────────────────
    brand_doc = None
    brand_domain = extraction.brand_domain or sender_email.split("@")[-1]
    if brand_domain:
        brand_doc = await db.brands.find_one({
            "$or": [
                {"domain": brand_domain},
                {"name": {"$regex": f"^{extraction.brand_name}$", "$options": "i"}} if extraction.brand_name else {}
            ]
        })

    brand_reliability = brand_doc.get("payment_intelligence", {}).get("payment_reliability", 0.5) if brand_doc else 0.5
    brand_avg_days = brand_doc.get("payment_intelligence", {}).get("avg_payment_days") if brand_doc else None
    brand_is_new = brand_doc is None or brand_doc.get("payment_intelligence", {}).get("total_deals_on_platform", 0) == 0

    # ── Step 2: Atlas Vector Search — similar deals ───────────────────────────
    # Build search text from extraction + subject (both describe the deal type)
    search_text = " ".join(filter(None, [
        subject,
        extraction.deal_type,
        extraction.brand_category,
        " ".join(extraction.deliverables or []),
    ]))
    similar_deals = await find_similar_deals(db, creator_id, search_text)
    similar_summary = summarise_similar_deals(similar_deals)

    # ── Step 3: Skills Map preference query ───────────────────────────────────
    preferences = await db.skills_map.find(
        {
            "creator_id": creator_id,
            "type": "preference",
            "evidence.confidence": {"$gte": 0.70},
        }
    ).to_list(20)

    # ── Step 4: Rate benchmark from niche_graph ───────────────────────────────
    market_benchmark = None
    if niche and follower_tier and extraction.deal_type:
        market_benchmark = await db.niche_graph.find_one({
            "niche": niche,
            "follower_tier": follower_tier,
            "content_format": extraction.deal_type,
            "confidence_weight": {"$gte": 0.40},
        })

    market_p50 = market_benchmark.get("rate_p50") if market_benchmark else None
    market_p25 = market_benchmark.get("rate_p25") if market_benchmark else None
    market_p75 = market_benchmark.get("rate_p75") if market_benchmark else None
    benchmark_confidence = market_benchmark.get("confidence_weight", 0.0) if market_benchmark else 0.0

    # Rate gap calculation (only if both amounts are known and non-ambiguous)
    rate_gap_pct = None
    offered = extraction.amount_typical if not extraction.amount_ambiguity_flag else None
    if offered and market_p50:
        rate_gap_pct = round((offered - market_p50) / market_p50 * 100, 1)

    # ── Step 5: Build flags ────────────────────────────────────────────────────
    flags: List[DraftFlag] = []

    if brand_is_new:
        flags.append(DraftFlag(
            flag_type="first_time_brand",
            severity="low",
            message=f"No prior history with {extraction.brand_name or brand_domain}.",
            recommended_action="Be professional but ensure payment terms are clear."
        ))

    if brand_doc and brand_reliability < 0.6:
        flags.append(DraftFlag(
            flag_type="brand_slow_payer",
            severity="high",
            message=f"{extraction.brand_name or brand_domain} has a payment reliability score of {brand_reliability:.0%}.",
            recommended_action="Consider requesting partial upfront payment."
        ))

    if extraction.exclusivity_duration_days and extraction.exclusivity_duration_days > 30:
        # Check creator's standard from skills_map
        exclusivity_standard = next(
            (p for p in preferences if "exclusivity" in p.get("name", "").lower()),
            None
        )
        flags.append(DraftFlag(
            flag_type="exclusivity_too_long",
            severity="medium",
            message=f"Exclusivity of {extraction.exclusivity_duration_days} days proposed. Your standard is typically shorter.",
            recommended_action=f"Counter-propose 30 days exclusivity."
        ))

    if rate_gap_pct is not None and rate_gap_pct < -15:
        flags.append(DraftFlag(
            flag_type="rate_below_market",
            severity="medium",
            message=f"Offered rate is {abs(rate_gap_pct):.0f}% below market P50 (₹{market_p50:,.0f}) for your tier.",
            recommended_action=f"Counter with ₹{market_p50:,.0f} or closer to your standard rate."
        ))

    if not extraction.payment_terms_mentioned:
        if brand_avg_days and brand_avg_days > 45:
            flags.append(DraftFlag(
                flag_type="brand_slow_payer",
                severity="medium",
                message=f"{extraction.brand_name or brand_domain} typically takes {brand_avg_days:.0f} days to pay. No payment terms mentioned in this email.",
                recommended_action="Specify NET-30 or 50% upfront in your reply."
            ))

    if extraction.amount_ambiguity_flag:
        flags.append(DraftFlag(
            flag_type="amount_ambiguous",
            severity="low",
            message="Deal amount not clearly stated. Draft will not include a rate counter-proposal.",
            recommended_action="Ask for their rate card or propose your standard rate in the reply."
        ))

    if extraction.is_agency_contact:
        flags.append(DraftFlag(
            flag_type="agency_contact",
            severity="low",
            message="This appears to be a PR agency contacting on behalf of the brand.",
            recommended_action="Confirm the end brand and ask for direct brand contact for contract."
        ))

    has_high = any(f.severity == "high" for f in flags)

    # ── Step 5: Complexity scoring → choose model ────────────────────────────
    thread_lower = sanitised_thread_text.lower()
    is_complex = any(signal in thread_lower for signal in COMPLEXITY_SIGNALS)
    model_to_use = DRAFT_MODEL_PRO if is_complex else DRAFT_MODEL_FLASH

    # ── Step 6: Call A — Draft generation ────────────────────────────────────
    from backend.services.gemini_client import get_gemini_client_genai
    client = get_gemini_client_genai()

    # Serialise all context for the prompt
    deal_context = {
        "brand_name": extraction.brand_name,
        "brand_domain": brand_domain,
        "brand_category": extraction.brand_category,
        "brand_reliability_score": round(brand_reliability, 2),
        "brand_is_new": brand_is_new,
        "deal_type": extraction.deal_type,
        "deliverables": extraction.deliverables,
        "offered_amount_inr": offered,
        "offered_amount_ambiguous": extraction.amount_ambiguity_flag,
        "offered_amount_raw": extraction.amount_raw_text,
        "market_p50_inr": market_p50,
        "market_p25_inr": market_p25,
        "rate_gap_percentage": rate_gap_pct,
        "exclusivity_mentioned": extraction.exclusivity_mentioned,
        "exclusivity_duration_days": extraction.exclusivity_duration_days,
        "payment_terms_mentioned": extraction.payment_terms_mentioned,
        "similar_deals_context": similar_summary,
        "flags_raised": [f.flag_type for f in flags],
        "creator_preferences": [
            {"name": p.get("name"), "polarity": p.get("preference", {}).get("polarity"), "value": p.get("preference", {}).get("value")}
            for p in preferences
        ],
    }

    voice_context = {
        "formality_score": voice_profile.get("formality_score", 3.0),
        "formality_label": voice_profile.get("formality_label", "neutral"),
        "emoji_frequency": voice_profile.get("emoji_frequency", 0),
        "top_emojis": voice_profile.get("top_emojis", []),
        "avg_response_length": voice_profile.get("avg_response_length", 80),
        "hindi_english_ratio": voice_profile.get("hindi_english_ratio", 0.0),
        "common_openers": voice_profile.get("common_openers", ["Hi,"]),
        "common_closers": voice_profile.get("common_closers", ["Best,"]),
        "uses_caps_emphasis": voice_profile.get("uses_caps_emphasis", False),
    }

    prompt_a = f"""
Voice profile (match this exactly):
{json.dumps(voice_context, indent=2)}

Deal context:
{json.dumps(deal_context, indent=2)}

Original email thread:
Subject: {subject}
From: {sender_email}
{sanitised_thread_text[:2000]}

Write the reply email body now. Match the voice profile exactly. Address the deal context. Return only the email body text.
"""

    draft_text = ""
    try:
        response_a = await asyncio.to_thread(
            client.models.generate_content,
            model=model_to_use,
            contents=prompt_a,
            config=types.GenerateContentConfig(
                system_instruction=DRAFT_SYSTEM_PROMPT,
                temperature=0.3,           # slight creativity for natural language
                max_output_tokens=600,
            )
        )
        draft_text = response_a.text.strip()
    except Exception as e:
        logger.error(f"Deal Chief draft generation error: {e}")
        draft_text = "Unable to generate draft. Please compose your reply manually."

    # ── Step 7: Call B — Voice compliance evaluation ──────────────────────────
    compliance = await evaluate_voice_compliance(draft_text, voice_profile)

    # Regenerate once if compliance score is below threshold
    if compliance.voice_compliance_score < 0.75 and draft_text != "Unable to generate draft. Please compose your reply manually.":
        logger.info(f"Voice compliance {compliance.voice_compliance_score:.2f} below threshold. Regenerating with tighter constraints.")
        specific_issues_text = "; ".join(compliance.specific_issues)
        tighter_prompt = f"""
{prompt_a}

VOICE CORRECTION REQUIRED. Previous draft had these issues: {specific_issues_text}
Fix these specific issues in your new draft. Everything else should remain the same.
"""
        try:
            response_retry = await asyncio.to_thread(
                client.models.generate_content,
                model=model_to_use,
                contents=tighter_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=DRAFT_SYSTEM_PROMPT,
                    temperature=0.1,       # lower temperature for tighter adherence
                    max_output_tokens=600,
                )
            )
            draft_text = response_retry.text.strip()
            # Re-evaluate
            compliance = await evaluate_voice_compliance(draft_text, voice_profile)
        except Exception as e:
            logger.error(f"Retry generation error: {e}")
            # Keep original draft with warning

    latency_ms = int((time.time() - start_time) * 1000)

    return DraftResult(
        thread_id=thread_id,
        creator_id=creator_id,
        brand_name=extraction.brand_name,
        brand_domain=brand_domain,
        brand_reliability_score=brand_reliability,
        brand_is_new=brand_is_new,
        offered_amount=offered,
        offered_amount_ambiguous=extraction.amount_ambiguity_flag,
        market_p50=market_p50,
        market_p25=market_p25,
        market_p75=market_p75,
        rate_gap_percentage=rate_gap_pct,
        benchmark_confidence=benchmark_confidence,
        similar_deals_found=len(similar_deals),
        similar_deals_summary=similar_summary,
        draft_text=draft_text,
        model_used=model_to_use,
        voice_compliance_score=compliance.voice_compliance_score,
        voice_compliance_issues=compliance.specific_issues,
        flags=flags,
        has_high_severity_flags=has_high,
        generation_latency_ms=latency_ms,
    )
```

---

## PART 6 — DEALS ROUTER

Build in `backend/routers/deals.py`:

```python
# backend/routers/deals.py

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/deals/inbound")
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
            brand = await db.brands.find_one({"_id": ObjectId(deal["brand_id"])})
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


@router.post("/deals/generate-draft/{deal_id}")
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


@router.get("/deals/draft/{deal_id}")
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


@router.post("/deals/approve/{deal_id}")
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
        from backend.services.gmail_sender import send_gmail_reply
        sent_message_id = await send_gmail_reply(
            creator_id=creator_id,
            thread_id=deal["raw_signals"]["gmail_thread_id"],
            body_text=final_text,
        )

        # ── Create Calendar follow-up reminder ────────────────────────────────
        calendar_event_id = None
        try:
            from backend.services.calendar_service import create_followup_event
            follow_up_date = datetime.utcnow() + timedelta(days=follow_up_days)
            brand_name = deal.get("brand_name") or draft.get("brand_name", "Brand")
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
        from backend.models.common import AgentActionType, ActionResult, DataClassificationTier
        from backend.services.mongodb_writer import write_with_classification
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


@router.post("/deals/reject/{deal_id}")
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

    await db.deal_drafts.update_one(
        {"deal_id": deal_id, "creator_id": creator_id, "creator_action": None},
        {"$set": {"creator_action": "rejected", "rejection_reason": reason}},
        sort=[("generated_at", -1)]
    )
    await db.deals.update_one(
        {"_id": ObjectId(deal_id)},
        {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}}
    )
    return {"status": "ok", "message": "Deal marked as rejected."}
```

---

## PART 7 — GMAIL SENDER + CALENDAR SERVICE

These are new services that the Deal Chief depends on.

### backend/services/gmail_sender.py

```python
# backend/services/gmail_sender.py

import asyncio
import base64
import logging
from email.mime.text import MIMEText
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


async def send_gmail_reply(
    creator_id: str,
    thread_id: str,
    body_text: str,
) -> str:
    """
    Sends a reply to an existing Gmail thread.
    Requires gmail.send scope — ensure this is in the OAuth consent screen.
    Returns the sent message ID.

    IMPORTANT: This is only called from /deals/approve/{deal_id}.
    ACTION_POLICY enforces that send_email ALWAYS requires creator approval.
    This function is the execution step AFTER that approval.
    """
    from backend.services.gmail_auth import get_gmail_credentials
    credentials = await get_gmail_credentials(creator_id)
    service = build("gmail", "v1", credentials=credentials)

    # Build the MIME message
    message = MIMEText(body_text, "plain", "utf-8")
    message["threadId"] = thread_id

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    sent = await asyncio.to_thread(
        lambda: service.users().messages().send(
            userId="me",
            body={
                "raw": raw_message,
                "threadId": thread_id,
            }
        ).execute()
    )

    logger.info(f"Gmail reply sent. Message ID: {sent['id']} Thread: {thread_id}")
    return sent["id"]
```

### backend/services/calendar_service.py

```python
# backend/services/calendar_service.py

import asyncio
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


async def create_followup_event(
    creator_id: str,
    title: str,
    date: datetime,
    description: str = "",
) -> str:
    """
    Creates a Google Calendar event as a follow-up reminder.
    Returns the event ID.
    """
    from backend.services.gmail_auth import get_gmail_credentials
    # Calendar uses same OAuth credentials as Gmail if scope includes calendar.events
    credentials = await get_gmail_credentials(creator_id)
    service = build("calendar", "v3", credentials=credentials)

    event = {
        "summary": title,
        "description": description,
        "start": {
            "date": date.strftime("%Y-%m-%d"),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "date": (date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 480},  # 8 hours before
            ],
        },
    }

    created = await asyncio.to_thread(
        lambda: service.events().insert(
            calendarId="primary",
            body=event,
        ).execute()
    )

    logger.info(f"Calendar event created: {created['id']} for creator {creator_id}")
    return created["id"]
```

---

## PART 8 — BACKGROUND ORCHESTRATOR FOR DEAL CHIEF

Add to `backend/routers/deals.py`:

```python
async def run_deal_chief_for_deal(deal_id: str, creator_id: str):
    """
    Background function: fetches deal context and runs Deal Chief pipeline.
    Pushes DraftResult to creator via SSE when complete.
    Stores DraftResult in deal_drafts collection.
    """
    from backend.services.deal_chief import run_deal_chief_pipeline
    from backend.services.sse_manager import publish_sse_event
    from backend.models.deal import DealExtraction
    from backend.services.mongodb_writer import write_with_classification
    from backend.models.common import DataClassificationTier

    db = get_db_singleton()

    try:
        deal = await db.deals.find_one({"_id": ObjectId(deal_id)})
        if not deal:
            return

        # Reconstruct minimal DealExtraction from stored deal document
        extraction = DealExtraction(
            brand_name=deal.get("brand_name"),
            brand_domain=deal.get("raw_signals", {}).get("brand_domain") or
                         (deal.get("raw_signals", {}).get("brand_contact_email", "").split("@")[-1]),
            brand_category=deal.get("brand_category"),
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
            payment_terms_mentioned=deal.get("raw_signals", {}).get("payment_terms_mentioned"),
            is_agency_contact=deal.get("raw_signals", {}).get("is_agency_contact", False),
            gmail_thread_id=deal.get("raw_signals", {}).get("gmail_thread_id", ""),
            sender_email=deal.get("raw_signals", {}).get("brand_contact_email", ""),
            extraction_confidence=deal.get("extraction_confidence", 0.7),
        )

        # Note: sanitised thread text is not stored (Principle 3).
        # For the Deal Chief pipeline, we use a short summary from the extraction
        # rather than the full thread text. The draft quality is slightly lower
        # than if we had the full thread, but privacy compliance is maintained.
        thread_summary = f"Brand deal email from {extraction.brand_domain}. " \
                        f"Deliverables: {', '.join(extraction.deliverables)}. " \
                        f"{'Amount: ₹' + str(extraction.amount_typical) if extraction.amount_typical else 'Amount: not stated'}."

        draft_result = await run_deal_chief_pipeline(
            db=db,
            creator_id=creator_id,
            thread_id=deal.get("raw_signals", {}).get("gmail_thread_id", deal_id),
            sanitised_thread_text=thread_summary,
            sender_email=extraction.sender_email or "",
            subject=deal.get("subject", ""),
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
        await publish_sse_event(creator_id, {
            "event": "draft_error",
            "deal_id": deal_id,
            "message": "Could not generate draft. Please compose manually.",
        })
```

---

## PART 9 — NEW COLLECTION: deal_drafts

Add to `backend/database/mongodb.py` in `create_indexes()`:

```python
# deal_drafts collection
await db.deal_drafts.create_index("creator_id")
await db.deal_drafts.create_index("deal_id")
await db.deal_drafts.create_index([("creator_id", 1), ("creator_action", 1)])
await db.deal_drafts.create_index([("creator_id", 1), ("generated_at", -1)])
```

Also add `gmail.send` and `calendar.events` scopes to the Gmail OAuth flow. In `backend/services/gmail_auth.py`, update `SCOPES`:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",        # NEW for Session 4
    "https://www.googleapis.com/auth/calendar.events",   # NEW for Session 4
]
```

**Important:** Adding new scopes requires existing users to re-authenticate. In dev this is fine. In production (Session 6), show a "ThreadComb needs additional permissions to send replies and create calendar events" prompt.

---

## PART 10 — FRONTEND: DEAL INBOX + APPROVAL UI

### Deal Inbox — `frontend/src/app/dashboard/deals/page.tsx`

This is a new page showing all inbound deals with their draft status.

**Layout:** List of DealCards. Header shows total count + "X drafts waiting for your approval". Sort: drafts pending first, then unanswered, then negotiating.

Each **DealCard** shows:
- Brand name + domain
- Deal type (instagram_reel, youtube_integration, etc.)
- Amount (if known) or "Amount not stated"
- Brand reliability score (BrandScoreBar component)
- Flag count with severity indicator
- "View Draft" button if draft exists
- "Generate Draft" button if no draft yet
- Date received

### Shadow Draft Modal — `frontend/src/components/ShadowDraftModal.tsx`

Full-screen modal (or slide-over) with two panels:

**Left panel — Context:**
- Brand name + reliability score (BrandScoreBar)
- Offered amount vs. market P50 (rate comparison bar)
- Similar deals summary ("You've done 3 similar deals at ₹45K–₹65K")
- FlagsPanel — all flags with severity colours
- Voice compliance score (small indicator — not prominently shown, it's internal quality)

**Right panel — Draft:**
- Editable textarea with the draft text (pre-filled with generated draft)
- Character count
- Language tag (EN / HI-EN)
- Four action buttons:
  - **"Approve & Send"** (primary, green) — sends exact draft text
  - **"Edit & Send"** (secondary) — user edits textarea then sends
  - **"Revise"** (tertiary) — asks AI to revise with a note
  - **"Reject"** (ghost, red) — marks as rejected, no email sent

On "Approve & Send": POST `/deals/approve/{deal_id}` with `{final_text: draft_text, action: "approved"}`.
On "Edit & Send": POST `/deals/approve/{deal_id}` with `{final_text: edited_text, action: "edited"}`.
On "Reject": POST `/deals/reject/{deal_id}`.

**BrandScoreBar component:**
```tsx
// Renders a coloured reliability bar: 0–0.4 red, 0.4–0.7 amber, 0.7–1.0 green
// Score: e.g. 0.82 shows as "Payment reliability: 82% — Good payer"
```

**FlagsPanel component:**
```tsx
// Renders each DraftFlag as a coloured alert card
// high severity: red border, bold text
// medium severity: amber border
// low severity: blue border, muted text
```

**After successful send:**
- Close the modal
- Show a toast: "Reply sent to [Brand]. Follow-up reminder set for [date]."
- Mark the DealCard as "Replied — awaiting response"
- Update SSE: push event to any open connections

---

## PART 11 — REAL-TIME SHADOW DRAFT (new email trigger)

When a new email arrives via the Gmail push webhook and passes the gate as `DEAL_SIGNAL`, the Deal Chief should be triggered automatically — not just queued for extraction.

Add to `backend/routers/ingestion.py` in `run_incremental_ingestion()`:

```python
# After gate classification passes as deal_signal in incremental ingestion:
# Enqueue for extraction (existing) AND trigger Deal Chief immediately

if gate_result.gate_decision in (GateDecision.DEAL_SIGNAL, GateDecision.HINDI_MIXED):
    # Existing: queue for full extraction
    await enqueue_thread_for_extraction(...)

    # NEW: Immediately trigger a preliminary Deal Chief run
    # This uses the gate-level data only (no full extraction yet)
    # The creator sees a "New brand deal detected" SSE event within seconds
    await publish_sse_event(creator_id, {
        "event": "new_deal_detected",
        "message": f"New brand deal email from {sanitised.sender_email.split('@')[-1]}",
        "brand_domain": sanitised.sender_email.split("@")[-1],
        "subject": sanitised.subject,
        "action": "Extraction in progress — draft will be ready in ~30 seconds",
    })
    # Full draft is generated after extraction completes (Session 3 worker triggers Session 4)
```

Add to the extraction worker (`extract_thread.py`), at the END of `run_extraction_worker()`, after deal is written:

```python
# After successful deal write: trigger Deal Chief pipeline
background_tasks = None  # not available in worker directly
# Instead: use db.deal_pipeline_queue to signal Deal Chief
# Or: call run_deal_chief_for_deal directly as background coroutine
asyncio.create_task(
    run_deal_chief_for_deal(deal_id=deal_id, creator_id=creator_id)
)
```

---

## PART 12 — ADD DEAL DRAFTS TO DASHBOARD

On the main dashboard page, add a "Deals needing attention" widget:

```tsx
// In dashboard/page.tsx — show when audit_complete and deals exist

<DealsSummaryWidget creatorId={creatorId} />
```

`DealsSummaryWidget` fetches `/deals/inbound` and shows:
- Count of pending drafts with "Review" button → navigates to /dashboard/deals
- Count of unanswered deals with "Generate Drafts" button

---

## EXIT CRITERIA — ALL MUST PASS BEFORE SESSION 5

1. **Deal Chief pipeline runs:** POST `/deals/generate-draft/{deal_id}` for a deal that exists in MongoDB. Confirm an SSE `draft_ready` event arrives. Confirm a `deal_drafts` document appears in MongoDB.

2. **Atlas Vector Search query uses RETRIEVAL_QUERY:** In the embedding call within `deal_search.py`, confirm `task_type="RETRIEVAL_QUERY"` is set. This is different from the `RETRIEVAL_DOCUMENT` used in Session 3 indexing.

3. **Two-model voice compliance:** Add a log line to `voice_compliance.py` confirming it makes an independent Gemini call. Confirm in application logs that two separate API calls are made per draft (generator + evaluator).

4. **Voice compliance below threshold triggers retry:** Manually set a test draft with intentionally wrong formality (very formal for a casual creator). Confirm the retry fires and the `specific_issues` list is populated.

5. **Flags generated correctly:** For a deal with `exclusivity_duration_days = 90`, confirm `DraftFlag(flag_type="exclusivity_too_long")` appears in the draft result.

6. **Approve & Send sends real Gmail:** POST `/deals/approve/{deal_id}` with `final_text`. Confirm the email appears in the Gmail "Sent" folder for the test creator account.

7. **Calendar event created:** Confirm a Google Calendar event titled "Follow up: [Brand] deal" appears on the creator's calendar 3 days from the approval.

8. **deal_drafts collection populated:** After approval, confirm the deal_drafts document has `creator_action: "approved"`, `sent_at` timestamp, and `final_text` set.

9. **Rejection works:** POST `/deals/reject/{deal_id}`. Confirm deal status updates to "rejected" and no email is sent.

10. **Dashboard shows deal count:** With at least one inbound deal in MongoDB, confirm the DealsSummaryWidget on the dashboard shows the correct count and "Review" button navigates to /dashboard/deals.

11. **New deal SSE event:** Trigger a new email via the Gmail webhook with a brand deal. Confirm `new_deal_detected` SSE event fires within 30 seconds. Confirm `draft_ready` SSE event fires within 60 seconds after that.

12. **No Gmail send without approval:** Search codebase for any call to `send_gmail_reply()` outside of the `/deals/approve/{deal_id}` endpoint handler. Confirm none exist. The ACTION_POLICY constraint must be structural, not just documented.

---

## NOTES FOR COPILOT AGENT

- `deal_drafts` is a new collection — add to create_indexes() and the collection-existence checks.
- The `gmail.send` and `calendar.events` scopes require adding to SCOPES in gmail_auth.py. Existing dev users will need to re-auth (delete their cookie, log in again).
- `asyncio.create_task()` in the worker requires a running event loop. The FastAPI background task context has one. If you hit "no running event loop" errors, use `background_tasks.add_task()` instead and pass it through from the endpoint.
- The shadow draft modal should use the existing shadcn/ui Dialog or Sheet component for consistency with Session 1's design system.
- Brand reliability score thresholds: < 0.40 = Poor (red), 0.40–0.69 = Fair (amber), ≥ 0.70 = Good (green). Show these consistently in both BrandScoreBar and FlagsPanel.
- The `RETRIEVAL_QUERY` vs `RETRIEVAL_DOCUMENT` distinction in task_type is critical for Atlas Vector Search quality. Index time: DOCUMENT. Query time: QUERY. Never mix them.
- For the "Revise" button: POST `/deals/generate-draft/{deal_id}` with an additional `revision_note` body parameter. The Deal Chief re-runs with the note appended to the prompt context.
- All datetime values: `datetime.utcnow()`. No `datetime.now()`.

---

*ThreadComb Session 4 — Deal Chief complete.*
*New brand deal arrives. Draft ready in 30 seconds. One tap to send.*
*The creator just recovered their first lost deal.*
