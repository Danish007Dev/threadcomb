from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from bson import ObjectId
from datetime import datetime
import logging

from routers.auth import get_current_creator
from database.mongodb import get_db_singleton

router = APIRouter()
logger = logging.getLogger(__name__)


def _stringify_object_ids(obj):
    """
    Recursively converts ObjectId and datetime instances to strings
    in a dictionary or list, making it JSON serializable.
    """
    if isinstance(obj, dict):
        return {k: _stringify_object_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_stringify_object_ids(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@router.get("/settings/export")
async def export_skills_map(request: Request, current_creator=Depends(get_current_creator)):
    """
    Exports the creator's complete Skills Map as JSON.
    DPDP data portability right — must work correctly.
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    export = {
        "creator_id": creator_id,
        "exported_at": datetime.utcnow().isoformat(),
        "export_version": "1.0",
        "creator_profile": await db.creators.find_one(
            {"creator_id": creator_id},
            {"oauth_tokens": 0, "gmail_secret_path": 0}  # exclude sensitive fields
        ),
        "deals": await db.deals.find(
            {"creator_id": creator_id},
            {"embedding_vector": 0}  # exclude vectors (not human-readable)
        ).to_list(1000),
        "brands": await db.brands.find({"data_source": {"$ne": "pre_training"}}).to_list(200),
        "invoices": await db.invoices.find({"creator_id": creator_id}).to_list(500),
        "skills_map": await db.skills_map.find({"creator_id": creator_id}).to_list(200),
        "audit_reports": await db.audit_reports.find(
            {"creator_id": creator_id},
            sort=[("created_at", -1)],
            limit=5
        ).to_list(5),
    }

    # Convert ObjectIds to strings for JSON serialization
    export = _stringify_object_ids(export)

    return JSONResponse(
        content=export,
        headers={"Content-Disposition": f"attachment; filename=threadcomb_export_{creator_id[:8]}.json"}
    )


@router.delete("/settings/delete-account")
async def delete_account(request: Request, current_creator=Depends(get_current_creator)):
    """
    Permanently deletes all creator data — DPDP compliance.
    Deletes all personal_identifiable documents across all collections.
    Anonymised aggregate contributions to niche_graph are NOT deleted (legitimate basis).
    """
    creator_id = str(current_creator["_id"])
    db = get_db_singleton()

    collections_to_purge = [
        "creators", "deals", "invoices", "skills_map",
        "agent_actions", "deal_drafts", "invoice_followups",
        "audit_reports", "fan_signals", "fan_interactions",
        "fan_profiles", "response_templates",
    ]

    deletion_counts = {}
    for collection_name in collections_to_purge:
        if collection_name == "creators":
            result = await db[collection_name].delete_one({"creator_id": creator_id})
        else:
            result = await db[collection_name].delete_many({"creator_id": creator_id})
        deletion_counts[collection_name] = result.deleted_count

    # NOTE: niche_graph documents with data_source="creator_contributed" are NOT deleted.
    # These are anonymised aggregate contributions — no PII, legitimate basis to retain.
    # The creator cannot be re-identified from these documents.

    logger.info(f"Account deletion complete for creator {creator_id}. Counts: {deletion_counts}")
    return {
        "status": "deleted",
        "message": "All your personal data has been permanently deleted from ThreadComb.",
        "deletion_counts": deletion_counts,
    }
