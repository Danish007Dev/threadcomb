"""Voice profile extraction — analyses creator's outbound brand deal emails.

Voice profile runs as a separate pass after initial deal extraction, using
only the creator's OUTBOUND email text (their replies, not brand messages).
This separation from DealExtraction is intentional — voice is about writing
style, not deal signals.
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VOICE_PROFILER_MODEL = "gemini-2.5-flash"

VOICE_EXTRACTION_PROMPT = """\
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

    from services.gemini_client import get_gemini_client_genai, GeminiClient
    from google.genai import types

    VOICE_PROFILER_MODEL = GeminiClient.DEFAULT_MODEL

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
        profile["last_calibrated_at"] = datetime.now(timezone.utc).isoformat()
        profile["calibration_sample_count"] = min(len(outbound_emails), 30)
        return profile

    except Exception as e:
        logger.error(f"Voice profile extraction error: {e}")
        return None


async def run_voice_profiling(creator_id: str):
    """
    Background task: collects outbound emails and extracts voice profile.
    Stores result in creators.voice_profile_brand.
    """
    from database.mongodb import get_db_singleton

    db = get_db_singleton()

    # Collect outbound email snippets from processed deal threads
    # In a full implementation, we'd parse outbound messages from raw threads
    # For now, this is a placeholder that will be populated as threads are processed
    # The voice profile will be calibrated once sufficient data accumulates

    logger.info(f"Voice profiling triggered for creator {creator_id}")

    # TODO: In a full implementation, collect outbound emails from the ingestion pass
    # For now, skip if we don't have enough data
    logger.info(f"Voice profiling skipped for creator {creator_id} — insufficient data in initial implementation")
