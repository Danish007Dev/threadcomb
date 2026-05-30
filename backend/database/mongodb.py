"""MongoDB singleton connection, collection references, and index creation."""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import logging

from config import settings

logger = logging.getLogger(__name__)


# All 10 collections required by the ThreadComb spec.
COLLECTION_NAMES = [
    "creators",
    "brands",
    "deals",
    "invoices",
    "skills_map",
    "agent_actions",
    "fan_interactions",
    "fan_profiles",
    "response_templates",
    "niche_graph",
]


class MongoDBSingleton:
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        if cls._client is None:
            cls._client = AsyncIOMotorClient(settings.MONGO_URL)
        return cls._client

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        if cls._db is None:
            cls._db = cls.get_client()[settings.DB_NAME]
        return cls._db

    @classmethod
    def close(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None


def get_db() -> AsyncIOMotorDatabase:
    return MongoDBSingleton.get_db()


def get_db_singleton() -> AsyncIOMotorDatabase:
    """Application-scoped Motor database for background tasks and workers.

    Use this in background tasks and Cloud Tasks workers — NOT in request handlers
    that already use Depends(get_db). Background tasks must not depend on
    request-scoped resources because the request may complete before the task runs.
    """
    return MongoDBSingleton.get_db()


async def ensure_collections(db: AsyncIOMotorDatabase) -> None:
    """Create any missing collections (MongoDB lazy-creates on write, but we want
    them visible from day one so Atlas UI shows all 10)."""
    existing = await db.list_collection_names()
    for name in COLLECTION_NAMES:
        if name not in existing:
            await db.create_collection(name)
            logger.info("Created collection: %s", name)


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all indexes required by ThreadComb."""
    # creators
    await db.creators.create_index("creator_id", unique=True)
    await db.creators.create_index("google_sub", sparse=True)
    await db.creators.create_index("email", unique=True)
    await db.creators.create_index("niche")

    # creator_sessions (for Google OAuth app sessions)
    await db.creator_sessions.create_index("session_token", unique=True)
    await db.creator_sessions.create_index("creator_id")

    # brands
    await db.brands.create_index("domain", unique=True)
    await db.brands.create_index("name")
    await db.brands.create_index("category")

    # deals
    await db.deals.create_index("creator_id")
    await db.deals.create_index([("creator_id", 1), ("status", 1)])
    await db.deals.create_index([("creator_id", 1), ("initiated_at", -1)])

    # invoices
    await db.invoices.create_index("creator_id")
    await db.invoices.create_index([("creator_id", 1), ("status", 1)])
    await db.invoices.create_index([("creator_id", 1), ("days_overdue", -1)])

    # skills_map
    await db.skills_map.create_index("creator_id")
    await db.skills_map.create_index([("creator_id", 1), ("type", 1)])

    # agent_actions
    await db.agent_actions.create_index("creator_id")
    await db.agent_actions.create_index("executed_at")
    await db.agent_actions.create_index([("creator_id", 1), ("action_type", 1)])

    # niche_graph
    await db.niche_graph.create_index(
        [("niche", 1), ("follower_tier", 1), ("content_format", 1)]
    )

    # ingestion_jobs (Session 2B)
    await db.ingestion_jobs.create_index("creator_id")
    await db.ingestion_jobs.create_index([("creator_id", 1), ("status", 1)])
    await db.ingestion_jobs.create_index("created_at")

    # response_templates
    await db.response_templates.create_index("creator_id")

    # fan_interactions
    await db.fan_interactions.create_index("creator_id")
    await db.fan_interactions.create_index("platform_message_id")

    # fan_profiles
    await db.fan_profiles.create_index([("creator_id", 1), ("platform_user_id", 1)])

    logger.info("All MongoDB indexes ensured.")
