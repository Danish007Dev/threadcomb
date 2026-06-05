"""Schema migrations for ThreadComb MongoDB.

Each function is idempotent. Safe to run multiple times.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

# Make `backend/` importable when this file is executed directly.
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Accept either MONGODB_URI (canonical) or MONGO_URL (legacy fallback).
if not os.environ.get("MONGODB_URI") and os.environ.get("MONGO_URL"):
    os.environ["MONGODB_URI"] = os.environ["MONGO_URL"]
if not os.environ.get("DB_NAME") and os.environ.get("MONGODB_DB_NAME"):
    os.environ["DB_NAME"] = os.environ["MONGODB_DB_NAME"]

from config import settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


async def migrate_niche_graph_v2(db=None) -> int:
    """Delete invalid Session 1 placeholder data from niche_graph.

    Conditions for deletion (any one is enough):
      - data_source == 'pre_training' AND missing source_type field
        (Session 1 docs never had source_type)
      - confidence_weight < 0.40 (below the defined minimum)
      - legacy 'confidence' field exists (old Session 1 schema field name)

    Documents where data_source == 'creator_contributed' are NEVER deleted
    (protects real production data).

    Returns the number of documents deleted.
    """
    own_client: Optional[AsyncIOMotorClient] = None
    if db is None:
        own_client = AsyncIOMotorClient(settings.MONGODB_URI)
        db = own_client[settings.DB_NAME]

    try:
        query = {
            "data_source": {"$ne": "creator_contributed"},
            "$or": [
                {"data_source": "pre_training", "source_type": {"$exists": False}},
                {"confidence_weight": {"$lt": 0.40}},
                {"confidence": {"$exists": True}},
            ],
        }
        result = await db.niche_graph.delete_many(query)
        print(
            f"Migration 2A: Deleted {result.deleted_count} invalid niche_graph documents "
            f"from Session 1"
        )
        logger.info("niche_graph migration 2A deleted %d documents.", result.deleted_count)
        return result.deleted_count
    finally:
        if own_client is not None:
            own_client.close()


if __name__ == "__main__":
    asyncio.run(migrate_niche_graph_v2())
