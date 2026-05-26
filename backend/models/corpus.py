"""Corpus / public-data extraction schemas.

Distinct from DealExtraction (which handles real creator Gmail data):
public-source extraction has no creator_id, a different confidence model,
and provenance fields.

These schemas are populated by Gemini Flash from documents in corpus/data/.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


NicheLiteral = Literal[
    "beauty", "gaming", "education", "finance", "fashion",
    "food", "tech", "sports", "asmr", "wellness", "politics", "gifting",
]
FollowerTierLiteral = Literal["nano", "micro", "mid", "macro", "mega"]
ContentFormatLiteral = Literal[
    "instagram_reel", "instagram_post", "instagram_story",
    "youtube_dedicated", "youtube_integration", "youtube_shorts",
    "multi_platform",
]
SourceTypeLiteral = Literal[
    "industry_report", "contract_template",
    "public_media_kit", "brand_signal", "disclosure_data",
]


class RateBenchmarkExtraction(BaseModel):
    """A single rate benchmark extracted from a public source.

    Multiple of these may come from a single document.
    """

    niche: Optional[NicheLiteral] = None
    follower_tier: Optional[FollowerTierLiteral] = None
    content_format: Optional[ContentFormatLiteral] = None
    rate_min: Optional[float] = None
    rate_max: Optional[float] = None
    rate_typical: Optional[float] = None  # midpoint or stated "typical"
    currency: str = "INR"
    geographic_scope: str = "india"
    observation_period: str  # when this data was collected/published
    source_quote: str  # exact phrase supporting the extraction (≤ 150 chars)
    extraction_confidence: float  # 0.0–1.0 — model self-assessment


class BrandSignalExtraction(BaseModel):
    """A brand actively running creator campaigns. Goes to `brands`, not niche_graph."""

    brand_name: str
    brand_domain: Optional[str] = None
    category: str  # "D2C_skincare", "gaming_peripheral", etc.
    niche_targeted: List[str] = Field(default_factory=list)
    content_formats_used: List[str] = Field(default_factory=list)
    campaign_activity_signal: bool = True
    geographic_scope: str = "india"
    observation_period: str
    source_quote: str
    extraction_confidence: float


class ClauseExtraction(BaseModel):
    """A contract clause pattern extracted from public templates."""

    clause_type: str  # "exclusivity", "payment_terms", "ip_ownership", etc.
    clause_summary: str
    creator_favourable: bool
    risk_level: int  # 1 (low) to 5 (high)
    typical_or_unusual: Literal["typical", "unusual", "red_flag"]
    source_quote: str
    extraction_confidence: float


class PublicDataExtraction(BaseModel):
    """Complete extraction output for one source document."""

    source_file: str
    source_type: SourceTypeLiteral
    document_date: Optional[str] = None
    geographic_scope: str = "india"

    rate_benchmarks: List[RateBenchmarkExtraction] = Field(default_factory=list)
    brand_signals: List[BrandSignalExtraction] = Field(default_factory=list)
    clauses: List[ClauseExtraction] = Field(default_factory=list)

    document_summary: str = ""
    total_extractions: int = 0
    processing_errors: List[str] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=_utcnow)
