"""Stage 0 ingestion gate — Gemini 2.5 Flash-Lite classifier.

Decides whether an email thread is a brand-deal signal worth running
through the full Stage 1 extraction (Session 3).

Cheap, deterministic where possible: a fast string-match spam check + a
token-length floor BEFORE the LLM call, so the model is never invoked on
obvious junk.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from models.ingestion import (
    GateClassificationResult,
    GateDecision,
    SanitisedThread,
)
from services.email_sanitiser import is_deterministic_spam, MIN_TOKEN_THRESHOLD

logger = logging.getLogger(__name__)

GATE_MODEL = "gemini-2.5-flash-lite"
HITL_THRESHOLD = 0.60

GATE_SYSTEM_PROMPT = """You are a binary classifier for email threads sent to content creators in India.

Determine if this email thread is a BRAND DEAL SIGNAL.

A BRAND DEAL SIGNAL involves ANY of:
- Brand/company reaching out about paid collaboration, sponsorship, or partnership
- Brand deal negotiation (counter-offers, contract terms, deliverables, rates)
- Invoice for completed brand deal
- Contract related to creator work
- PR/gifting request (free product in exchange for content)
- Payment follow-up for completed deal
- Media kit or rate card request

NOT a deal signal:
- Personal emails (family, friends)
- Shopping receipts, order confirmations, delivery notifications
- Newsletter subscriptions, app notifications
- Internal emails (sender and recipient share a domain)
- Google/Meta/YouTube platform notifications

Language detection:
- "en": primarily English
- "hi": primarily Hindi (Devanagari or transliteration)
- "hi-en": code-switched Hindi-English (very common for Indian creators: "bhai yeh collab ke liye kitna rate doge?")
- "other": another language

Set hindi_mode=true if language is "hi" or "hi-en".

Return ONLY valid JSON in this exact format, no markdown, no explanation:
{
  "is_deal_signal": true or false,
  "is_spam": true or false,
  "language": "en" or "hi" or "hi-en" or "other",
  "hindi_mode": true or false,
  "confidence": 0.0 to 1.0,
  "reasoning_brief": "one sentence max"
}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _low_confidence_result(thread_id: str, reason: str) -> GateClassificationResult:
    return GateClassificationResult(
        thread_id=thread_id,
        is_deal_signal=False,
        is_spam=False,
        language="en",
        hindi_mode=False,
        confidence=0.0,
        gate_decision=GateDecision.LOW_CONFIDENCE,
        reasoning_brief=reason,
        tokens_used=0,
    )


async def classify_thread_gate(
    sanitised_thread: SanitisedThread,
    gemini_client,
) -> GateClassificationResult:
    """Run the Stage 0 gate on a sanitised thread.

    Never raises — returns a LOW_CONFIDENCE or RATE_LIMITED result on error.
    Retries 429 errors with exponential backoff.
    """
    from config import settings

    thread_id = sanitised_thread.thread_id

    # 1) Deterministic spam check — zero LLM cost.
    if is_deterministic_spam(sanitised_thread.subject, sanitised_thread.sanitised_text):
        return GateClassificationResult(
            thread_id=thread_id,
            is_deal_signal=False,
            is_spam=True,
            language="en",
            hindi_mode=False,
            confidence=0.99,
            gate_decision=GateDecision.SPAM_DETECTED,
            reasoning_brief="Deterministic spam signal detected",
            tokens_used=0,
        )

    # 2) Token-length floor.
    if sanitised_thread.sanitised_token_count < MIN_TOKEN_THRESHOLD:
        return GateClassificationResult(
            thread_id=thread_id,
            is_deal_signal=False,
            is_spam=False,
            language="en",
            hindi_mode=False,
            confidence=0.85,
            gate_decision=GateDecision.NOT_DEAL_SIGNAL,
            reasoning_brief="Thread too short to contain deal information",
            tokens_used=0,
        )

    # 3) LLM gate classification with retry on 429.
    gate_input = (
        f"Subject: {sanitised_thread.subject}\n"
        f"Sender: {sanitised_thread.sender_email}\n"
        f"Thread preview: {sanitised_thread.sanitised_text[:600]}"
    )

    max_retries = getattr(settings, "GATE_MAX_RETRIES", 6)
    parsed = None
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            parsed = await gemini_client.send_json(
                system_message=GATE_SYSTEM_PROMPT,
                user_message=gate_input,
                model=GATE_MODEL,
            )
            last_error = None
            break  # success
        except json.JSONDecodeError as exc:
            logger.error("Gate JSON parse error for %s: %s", thread_id, exc)
            return _low_confidence_result(thread_id, f"JSON parse error: {str(exc)[:50]}")
        except Exception as exc:
            last_error = exc
            error_str = str(exc)
            is_rate_limited = "429" in error_str or "Too Many Requests" in error_str

            if is_rate_limited and attempt < max_retries:
                # Slower linear backoff for Free Tier (15 RPM limits): 10s, 20s, 30s, 40s...
                backoff = 10 * (attempt + 1)
                logger.warning(
                    "Gate 429 for %s (attempt %d/%d). Backing off %ds.",
                    thread_id, attempt + 1, max_retries, backoff
                )
                await asyncio.sleep(backoff)
                continue
            elif is_rate_limited:
                logger.error(
                    "Gate 429 for %s — all %d retries exhausted.", thread_id, max_retries
                )
                return GateClassificationResult(
                    thread_id=thread_id,
                    is_deal_signal=False,
                    is_spam=False,
                    language="en",
                    hindi_mode=False,
                    confidence=0.0,
                    gate_decision=GateDecision.RATE_LIMITED,
                    reasoning_brief=f"API rate limited after {max_retries} retries",
                    tokens_used=0,
                )
            else:
                logger.error("Gate classification failed for %s: %s", thread_id, exc)
                return _low_confidence_result(thread_id, f"Error: {str(exc)[:80]}")

    if parsed is None:
        return _low_confidence_result(thread_id, "Classification returned no result")

    is_deal = bool(parsed.get("is_deal_signal", False))
    is_spam = bool(parsed.get("is_spam", False))
    language = str(parsed.get("language", "en"))
    hindi_mode = bool(parsed.get("hindi_mode", False))
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(parsed.get("reasoning_brief", ""))

    if is_spam:
        decision = GateDecision.SPAM_DETECTED
    elif confidence < HITL_THRESHOLD:
        decision = GateDecision.LOW_CONFIDENCE
    elif hindi_mode and is_deal:
        decision = GateDecision.HINDI_MIXED
    elif is_deal:
        decision = GateDecision.DEAL_SIGNAL
    else:
        decision = GateDecision.NOT_DEAL_SIGNAL

    return GateClassificationResult(
        thread_id=thread_id,
        is_deal_signal=is_deal,
        is_spam=is_spam,
        language=language,
        hindi_mode=hindi_mode,
        confidence=confidence,
        gate_decision=decision,
        reasoning_brief=reasoning,
        tokens_used=0,
    )


# ── Fan Signal Detection (Session 3) ────────────────────────────────────────
# Fan signal keywords — checked AFTER brand deal gate.
# Only classify fan signals for threads that did NOT pass as deal signals.

FAN_SIGNAL_KEYWORDS = [
    "love your content", "huge fan", "inspired by", "your video helped",
    "could you do a video on", "tutorial request", "collaboration between creators",
    "your work is amazing", "can you review", "you should cover",
]


def detect_fan_signal(subject: str, text: str) -> Optional[str]:
    """
    Check if a non-deal thread contains fan signal keywords.
    Returns the signal_type if detected, None otherwise.
    """
    combined = f"{subject} {text}".lower()

    appreciation_keywords = ["love your content", "huge fan", "inspired by", "your work is amazing"]
    request_keywords = ["could you do a video on", "tutorial request", "can you review", "you should cover"]
    collab_keywords = ["collaboration between creators"]

    for kw in appreciation_keywords:
        if kw in combined:
            return "fan_appreciation"
    for kw in request_keywords:
        if kw in combined:
            return "content_request"
    for kw in collab_keywords:
        if kw in combined:
            return "creator_collab"

    # Check any remaining fan signal keywords
    for kw in FAN_SIGNAL_KEYWORDS:
        if kw in combined:
            return "general"

    return None
