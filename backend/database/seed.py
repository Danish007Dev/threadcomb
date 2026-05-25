"""niche_graph pre-training seed data.

These entries represent industry-benchmark knowledge derived from public sources.
Confidence starts at 0.3 (low) until real creator data reinforces it.
"""

from datetime import datetime, timezone
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from services.mongodb_writer import write_with_classification
from models.common import DataClassificationTier

logger = logging.getLogger(__name__)


# (niche, follower_tier, content_format, p50_INR)
SEED_NICHE_GRAPH = [
    ("beauty", "mid", "instagram_reel", 42500.0),
    ("beauty", "micro", "instagram_reel", 18000.0),
    ("gaming", "mid", "youtube_integration", 35000.0),
    ("finance", "mid", "youtube_dedicated", 55000.0),
    ("education", "mid", "youtube_dedicated", 45000.0),
    ("fashion", "micro", "instagram_reel", 15000.0),
    # extras for richer coverage
    ("beauty", "macro", "instagram_reel", 95000.0),
    ("tech", "mid", "youtube_dedicated", 50000.0),
    ("food", "mid", "instagram_reel", 32000.0),
    ("wellness", "mid", "instagram_reel", 28000.0),
]


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def seed_niche_graph(db: AsyncIOMotorDatabase) -> int:
    """Insert pre-training niche_graph data if the collection is empty.

    Returns the number of documents inserted.
    """
    existing_count = await db.niche_graph.count_documents({})
    if existing_count > 0:
        logger.info(
            "niche_graph already has %d documents — skipping seed.", existing_count
        )
        return 0

    period = _current_period()
    inserted = 0
    for niche, tier, content_format, p50 in SEED_NICHE_GRAPH:
        document = {
            "niche": niche,
            "follower_tier": tier,
            "geography": "IN",
            "content_format": content_format,
            "period": period,
            "rate_distribution": {
                "p10": round(p50 * 0.45, 2),
                "p25": round(p50 * 0.65, 2),
                "p50": p50,
                "p75": round(p50 * 1.55, 2),
                "p90": round(p50 * 2.10, 2),
                "sample_size": 0,
                "confidence": 0.3,
            },
            "brand_patterns": {},
            "clause_risk_index": [],
            "creator_count_contributing": 0,
            "data_source": "pre_training",
            "last_updated": datetime.now(timezone.utc),
        }
        await write_with_classification(
            db.niche_graph,
            document,
            classification_tier=DataClassificationTier.AGGREGATE,
            anonymisation_eligible=True,
            export_eligible=True,
        )
        inserted += 1

    logger.info("Seeded %d niche_graph documents.", inserted)
    return inserted
