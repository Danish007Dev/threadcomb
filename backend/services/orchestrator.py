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
from services.gemini_client import get_gemini_client_genai, GeminiClient

logger = logging.getLogger(__name__)

ROUTER_MODEL = GeminiClient.DEFAULT_MODEL

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
    from services.gemini_client import get_gemini_client_genai
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

    agent_descriptions = {
        "dna_reader": "Email Audit — scans your Gmail for brand deal signals and builds your Skills Map",
        "deal_chief": "Deal Manager — checks for unanswered brand deals and drafts replies",
        "revenue_guardian": "Invoice Guardian — finds overdue invoices and drafts follow-up emails",
        "all": "All agents — running Email Audit, Deal Manager, and Invoice Guardian",
    }

    yield {
        "event": "routing_complete",
        "agent": agent,
        "confidence": confidence,
        "message": f"Routing to {agent_descriptions.get(agent, agent)}...",
    }

    dispatched_agents = []

    # Step 3: Execute the routed agent(s)
    if agent == "dna_reader" or agent == "all":
        yield {"event": "agent_start", "agent": "dna_reader", "message": "Email Audit: scanning your Gmail for brand deal signals..."}

        # Create a real ingestion job to avoid ObjectId crash
        try:
            from models.ingestion import IngestionJob, IngestionTrigger
            from bson import ObjectId
            job = IngestionJob(
                creator_id=creator_id,
                trigger=IngestionTrigger.MANUAL,
                sse_channel=creator_id,
            )
            job_doc = job.model_dump()
            result = await db.ingestion_jobs.insert_one(job_doc)
            real_job_id = str(result.inserted_id)

            from routers.ingestion import run_full_ingestion
            asyncio.create_task(run_full_ingestion(creator_id=creator_id, job_id=real_job_id))
            dispatched_agents.append("Email Audit")
            yield {"event": "agent_dispatched", "agent": "dna_reader", "message": "Email Audit is running. Progress will appear on the dashboard."}
        except Exception as e:
            logger.error(f"Orchestrator failed to start ingestion: {e}")
            yield {"event": "agent_error", "agent": "dna_reader", "message": f"Could not start audit: {str(e)[:100]}"}

    if agent == "deal_chief" or agent == "all":
        yield {"event": "agent_start", "agent": "deal_chief", "message": "Deal Manager: checking for unanswered brand deals..."}
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
            
            from routers.deals import run_deal_chief_for_deal
            for deal in unanswered_deals:
                asyncio.create_task(
                    run_deal_chief_for_deal(
                        deal_id=str(deal["_id"]),
                        creator_id=creator_id,
                    )
                )
            dispatched_agents.append("Deal Manager")
        else:
            yield {"event": "agent_result", "agent": "deal_chief", "message": "No unanswered brand deals right now."}

    if agent == "revenue_guardian" or agent == "all":
        yield {"event": "agent_start", "agent": "revenue_guardian", "message": "Invoice Guardian: checking for overdue payments..."}
        overdue_count = await db.invoices.count_documents({
            "creator_id": creator_id,
            "status": {"$in": ["pending", "overdue"]},
            "days_overdue": {"$gt": 0},
        })
        if overdue_count > 0:
            yield {"event": "agent_result", "agent": "revenue_guardian", "message": f"Found {overdue_count} overdue invoice{'s' if overdue_count > 1 else ''}. Preparing follow-ups..."}
            from services.revenue_guardian import run_revenue_guardian
            asyncio.create_task(run_revenue_guardian(creator_id=creator_id))
            dispatched_agents.append("Invoice Guardian")
        else:
            yield {"event": "agent_result", "agent": "revenue_guardian", "message": "No overdue invoices. All payments on track."}

    # Build a specific completion message
    if dispatched_agents:
        running_text = ", ".join(dispatched_agents)
        message = f"{running_text} {'is' if len(dispatched_agents) == 1 else 'are'} running in the background. Results will update on the dashboard as they complete."
    else:
        message = "Nothing to do right now — no pending deals, overdue invoices, or new emails to scan."

    yield {
        "event": "orchestration_complete",
        "agent": agent,
        "message": message,
    }

