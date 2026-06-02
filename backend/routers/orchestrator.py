from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import json

from routers.auth import get_current_creator
from database.mongodb import get_db_singleton

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
        from services.orchestrator import orchestrate
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

    from services.orchestrator import route_deterministic, route_with_llm
    agent, confidence = route_deterministic(user_input)
    if not agent:
        agent, confidence = await route_with_llm(user_input)

    return {
        "routed_to": agent,
        "confidence": confidence,
        "message": f"Dispatched to {agent}. Check the relevant section for updates.",
    }
