"""Gemini Pro synthesis for the Audit Report (Session 3).

Calls Gemini Pro with the SynthesisContext and returns a typed SynthesisReport.
"""

import asyncio
import logging

from models.audit import SynthesisContext, SynthesisReport

logger = logging.getLogger(__name__)
SYNTHESIS_MODEL = "gemini-2.5-pro"

SYNTHESIS_SYSTEM_PROMPT = """\
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
    from services.gemini_client import get_gemini_client_genai
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
