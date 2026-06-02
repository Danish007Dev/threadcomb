"""MongoDB write helper — all writes go through write_with_classification().

Principle 4 — every MongoDB write must include a data_classification block.
No raw `collection.insert_one()` or `collection.update_one()` calls anywhere
else in the codebase. This module is the single chokepoint.
"""

from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
import logging

from models.common import DataClassificationTier

# Lazy import to prevent Uvicorn/Motor deadlock on Windows
if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

logger = logging.getLogger(__name__)


def _build_classification_block(
    classification_tier: DataClassificationTier,
    anonymisation_eligible: bool,
    export_eligible: bool,
) -> dict:
    return {
        "tier": classification_tier.value,
        "deletion_policy": "on_request_30d",
        "anonymisation_eligible": anonymisation_eligible,
        "export_eligible": export_eligible,
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }


def _serialize_datetimes(doc: dict) -> dict:
    """Recursively convert any datetime values to ISO strings for MongoDB safety."""
    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
        elif isinstance(value, dict):
            doc[key] = _serialize_datetimes(value)
        elif isinstance(value, list):
            doc[key] = [
                _serialize_datetimes(item) if isinstance(item, dict)
                else item.isoformat() if isinstance(item, datetime)
                else item
                for item in value
            ]
    return doc


async def write_with_classification(
    collection: "AsyncIOMotorCollection",
    document: dict,
    classification_tier: DataClassificationTier = DataClassificationTier.PERSONAL_IDENTIFIABLE,
    anonymisation_eligible: bool = False,
    export_eligible: bool = True,
) -> str:
    """Append data_classification to every document before writing.

    Returns the inserted document ID as string.
    All MongoDB inserts in ThreadComb must use this function.
    """
    document = dict(document)
    document["data_classification"] = _build_classification_block(
        classification_tier, anonymisation_eligible, export_eligible
    )
    now = datetime.now(timezone.utc)
    if "created_at" not in document:
        document["created_at"] = now
    document["updated_at"] = now

    document = _serialize_datetimes(document)

    result = await collection.insert_one(document)
    logger.info(
        "Wrote document %s to %s [tier: %s]",
        result.inserted_id,
        collection.name,
        classification_tier.value,
    )
    return str(result.inserted_id)


async def upsert_with_classification(
    collection: "AsyncIOMotorCollection",
    filter_query: dict,
    update_data: dict,
    classification_tier: DataClassificationTier = DataClassificationTier.PERSONAL_IDENTIFIABLE,
    anonymisation_eligible: bool = False,
    export_eligible: bool = True,
) -> None:
    """Upsert a document with data_classification block.

    Used for brands (upsert on domain), skills_map nodes, and onboarding patches.
    """
    update_data = dict(update_data)
    update_data["data_classification"] = _build_classification_block(
        classification_tier, anonymisation_eligible, export_eligible
    )
    update_data["updated_at"] = datetime.now(timezone.utc)

    update_data = _serialize_datetimes(update_data)

    await collection.update_one(
        filter_query,
        {
            "$set": update_data,
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )


async def update_with_classification(
    collection: "AsyncIOMotorCollection",
    filter_query: dict,
    update_data: dict,
    classification_tier: DataClassificationTier = DataClassificationTier.PERSONAL_IDENTIFIABLE,
    anonymisation_eligible: bool = False,
    export_eligible: bool = True,
) -> int:
    """Update an existing document while refreshing data_classification."""
    update_data = dict(update_data)
    update_data["data_classification"] = _build_classification_block(
        classification_tier, anonymisation_eligible, export_eligible
    )
    update_data["updated_at"] = datetime.now(timezone.utc)

    update_data = _serialize_datetimes(update_data)

    result = await collection.update_one(filter_query, {"$set": update_data})
    return result.modified_count