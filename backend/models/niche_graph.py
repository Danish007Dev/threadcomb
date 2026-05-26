"""niche_graph schema — Layer 2 anonymised creator economy intelligence.

Replaces the placeholder NicheGraphNode that lived in models/deal.py in Session 1.
Every document records its source provenance and a confidence_weight derived
from how many distinct source TYPES corroborate the benchmark.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone


def _utcnow() -> datetime:
    """Timezone-aware UTC now (ThreadComb standard)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Allowed values — kept as Literals so Pydantic enforces them strictly.
# ---------------------------------------------------------------------------

NicheLiteral = Literal[
    "beauty",
    "gaming",
    "education",
    "finance",
    "fashion",
    "food",
    "tech",
    "sports",
    "asmr",
    "wellness",
    "politics",
    "gifting",
]

FollowerTierLiteral = Literal["nano", "micro", "mid", "macro", "mega"]

ContentFormatLiteral = Literal[
    "instagram_reel",
    "instagram_post",
    "instagram_story",
    "youtube_dedicated",
    "youtube_integration",
    "youtube_shorts",
    "multi_platform",
]

SourceTypeLiteral = Literal[
    "industry_report",
    "contract_template",
    "public_media_kit",
    "brand_signal",
    "disclosure_data",
]


class NicheGraphNode(BaseModel):
    # Classification keys — composite unique key for upsert
    niche: NicheLiteral
    follower_tier: FollowerTierLiteral
    content_format: ContentFormatLiteral

    # Geographic and temporal scope
    geographic_scope: str = "india"
    observation_period: str  # e.g. "2024_annual", "Q4_2025", "2025_H1"

    # Rate distribution
    rate_p25: Optional[float] = None
    rate_p50: Optional[float] = None
    rate_p75: Optional[float] = None
    currency: str = "INR"

    # Sample metadata
    sample_size: int = 0
    creator_count_contributing: int = 0

    # Source provenance — REQUIRED for every document
    source_type: SourceTypeLiteral
    source_file: str  # exact filename, e.g. "asci_report_2024.pdf"

    # Confidence system
    confidence_weight: float  # 0.40–0.85 (pre-training), 0.90 (creator), 1.00 (human-reviewed)
    corroboration_score: float  # 0.33 (1 source type) → 0.67 (2) → 1.0 (3)
    corroboration_sources: List[str] = Field(default_factory=list)

    # Data lineage
    data_source: Literal["pre_training", "creator_contributed"] = "pre_training"

    # Quality flags
    flagged_for_review: bool = False
    outlier_reason: Optional[str] = None

    # Timestamps
    last_updated: datetime = Field(default_factory=_utcnow)
    created_at: datetime = Field(default_factory=_utcnow)

    # Data classification (ThreadComb standard)
    data_classification: dict = Field(
        default_factory=lambda: {
            "tier": "aggregate",
            "deletion_policy": "retain_anonymised",
            "anonymisation_eligible": True,
            "export_eligible": True,
        }
    )
