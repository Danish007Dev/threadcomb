"""niche_graph seed — DEPRECATED in Session 2A.

Session 1 seeded 10 hardcoded niche_graph documents with confidence=0.3.
The ThreadComb spec defines 0.40 as the minimum confidence (one industry source),
so those documents were invalid placeholders.

Session 2A introduces the corpus ingestion pipeline at backend/corpus/ingest.py
which populates niche_graph from real public-source documents with proper
provenance and confidence_weight. This function is now a no-op kept for
backwards-compatible imports from server.py startup.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


async def seed_niche_graph(db: AsyncIOMotorDatabase) -> int:
    """No-op. Run `python backend/corpus/ingest.py --folder ./corpus/data/`
    to populate niche_graph from real sources."""
    logger.info(
        "seed_niche_graph is a no-op as of Session 2A. "
        "Use the corpus ingestion pipeline instead."
    )
    return 0
