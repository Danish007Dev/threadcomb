from fastapi import APIRouter, Depends, Request
from bson import ObjectId
from datetime import datetime
import logging

from routers.auth import get_current_creator
from database.mongodb import get_db_singleton

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/hitl/queue")
async def get_hitl_queue(request: Request, current_creator=Depends(get_current_creator)):
    """Returns items pending human review."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    items = await db.agent_actions.find(
        {
            "creator_id": creator_id,
            "action_type": "hitl_queued",
            "outcome.result": "pending_hitl",
        },
        sort=[("executed_at", -1)],
        limit=20
    ).to_list(20)
    for item in items:
        item["_id"] = str(item["_id"])
    return items


@router.post("/hitl/resolve/{action_id}")
async def resolve_hitl_item(action_id: str, request: Request, current_creator=Depends(get_current_creator)):
    """Resolves a HITL queue item — either triggers extraction or discards."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    body = await request.json()
    resolution = body.get("resolution")  # "extract" or "discard"

    await db.agent_actions.update_one(
        {"_id": ObjectId(action_id), "creator_id": creator_id},
        {"$set": {
            "outcome.result": "hitl_resolved",
            "outcome.resolution": resolution,
            "outcome.resolved_at": datetime.utcnow(),
        }}
    )
    return {"status": "resolved", "resolution": resolution}


@router.get("/activity/recent")
async def get_recent_activity(request: Request, current_creator=Depends(get_current_creator)):
    """Returns the 15 most recent agent actions for the dashboard feed."""
    creator_id = current_creator["creator_id"]
    db = get_db_singleton()
    items = await db.agent_actions.find(
        {"creator_id": creator_id},
        sort=[("executed_at", -1), ("_id", -1)],
        limit=15
    ).to_list(15)
    for item in items:
        item["_id"] = str(item["_id"])
    return items


@router.get("/activity/all")
async def get_all_activity(
    request: Request, 
    agent: str = "all",
    outcome: str = "all",
    current_creator=Depends(get_current_creator)
):
    """Returns all agent actions with optional filtering."""
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()
    
    query = {"creator_id": creator_id}
    if agent != "all":
        query["agent"] = agent
    if outcome != "all":
        query["outcome.result"] = outcome
        
    items = await db.agent_actions.find(
        query,
        sort=[("executed_at", -1), ("_id", -1)],
        limit=100
    ).to_list(100)
    for item in items:
        item["_id"] = str(item["_id"])
    return items
