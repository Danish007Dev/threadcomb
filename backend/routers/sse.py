"""SSE endpoints for real-time ingestion progress."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from routers.auth import get_current_creator
from services.sse_manager import subscribe_sse

router = APIRouter(tags=["sse"])


@router.get("/sse/ingestion/{creator_id}")
async def ingestion_sse_stream(
    creator_id: str,
    request: Request,
    current_creator=Depends(get_current_creator),
):
    """SSE endpoint for ingestion progress events."""
    authenticated_creator_id = current_creator["creator_id"]
    if authenticated_creator_id != creator_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return StreamingResponse(
        subscribe_sse(creator_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
