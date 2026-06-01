# backend/services/deal_chief.py

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from google.genai import types

from models.draft import DraftResult, DraftFlag, VoiceComplianceResult
from services.deal_search import find_similar_deals, summarise_similar_deals
from services.voice_compliance import evaluate_voice_compliance

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
        # Try by creator_id string field (used by onboarding)
        creator = await db.creators.find_one({"creator_id": creator_id})
    if not creator:
        raise ValueError(f"Creator {creator_id} not found")

    voice_profile = creator.get("voice_profile_brand", {})
    niche = creator.get("niche")
    follower_tier = creator.get("follower_tier")

    # ── Step 1: Brand history lookup ──────────────────────────────────────────
    brand_doc = None
    brand_domain = extraction.brand_domain or sender_email.split("@")[-1]
    if brand_domain:
        # Build $or clauses safely — avoid empty dict (Bug 3 fix)
        or_clauses = [{"domain": brand_domain}]
        if extraction.brand_name:
            or_clauses.append({"name": {"$regex": f"^{extraction.brand_name}$", "$options": "i"}})
        brand_doc = await db.brands.find_one({"$or": or_clauses})

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

    # ── Step 5b: Complexity scoring → choose model ───────────────────────────
    thread_lower = sanitised_thread_text.lower()
    is_complex = any(signal in thread_lower for signal in COMPLEXITY_SIGNALS)
    model_to_use = DRAFT_MODEL_PRO if is_complex else DRAFT_MODEL_FLASH
    logger.info(f"Deal Chief: complexity={'complex' if is_complex else 'standard'}, model={model_to_use}")

    # ── Step 6: Call A — Draft generation ────────────────────────────────────
    from services.gemini_client import get_gemini_client_genai
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
    logger.info(f"Deal Chief: starting draft generation (Call A) for {extraction.brand_name or brand_domain}")
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
        logger.info(f"Deal Chief: Call A complete. Draft length={len(draft_text)} chars, model={model_to_use}")
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
