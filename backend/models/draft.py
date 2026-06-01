# backend/models/draft.py

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class DraftFlag(BaseModel):
    """A single flag raised during draft generation context analysis."""
    flag_type: Literal[
        "exclusivity_too_long",      # exclusivity duration > creator's standard
        "rate_below_market",         # offered rate < niche P50 by more than 15%
        "missing_kill_fee",          # no kill fee clause mentioned
        "payment_terms_unfavourable",# NET-60 when creator's standard is NET-30
        "brand_slow_payer",          # brand's avg_payment_days > 45
        "brand_overdue_history",     # brand has past overdue invoices
        "ip_rights_broad",           # IP ownership terms seem broad
        "first_time_brand",          # no prior history with this brand
        "agency_contact",            # PR agency contacting on behalf of brand
        "amount_ambiguous",          # deal amount not clearly stated
    ]
    severity: Literal["high", "medium", "low"]
    message: str                    # human-readable explanation for the creator
    recommended_action: Optional[str] = None  # what to do about this flag


class VoiceComplianceResult(BaseModel):
    """
    Output of Call B — the separate voice compliance evaluator.
    This model evaluates the draft from Call A without knowing it generated it.
    """
    voice_compliance_score: float   # 0.0–1.0. Below 0.75: regenerate or warn.
    formality_match: bool           # does formality level match voice_profile_brand?
    emoji_match: bool               # does emoji usage match profile?
    length_match: bool              # is response length appropriate to profile?
    hindi_integration_correct: bool # if creator code-switches, does draft match?
    specific_issues: List[str]      # list of specific voice mismatches found
    overall_assessment: str         # one sentence: why this score


class DraftResult(BaseModel):
    """Complete output of the Deal Chief pipeline for one inbound deal."""
    deal_id: Optional[str] = None   # MongoDB deal _id (set after deal document created)
    thread_id: str
    creator_id: str
    brand_name: Optional[str]
    brand_domain: Optional[str]
    brand_reliability_score: float  # 0.0–1.0 from brands.payment_intelligence
    brand_is_new: bool              # no prior deals with this brand

    # Rate context
    offered_amount: Optional[float] = None
    offered_amount_ambiguous: bool = False
    market_p50: Optional[float] = None
    market_p25: Optional[float] = None
    market_p75: Optional[float] = None
    rate_gap_percentage: Optional[float] = None  # negative = below market
    benchmark_confidence: float = 0.0

    # Similar deals context
    similar_deals_found: int = 0
    similar_deals_summary: Optional[str] = None  # "You've done 3 similar deals at ₹45K–₹65K"

    # The draft
    draft_text: str
    draft_language: str = "en"      # "en" | "hi" | "hi-en"
    model_used: str                  # "gemini-2.5-flash" or "gemini-2.5-pro"
    voice_compliance_score: float
    voice_compliance_issues: List[str] = []

    # Flags
    flags: List[DraftFlag] = []
    has_high_severity_flags: bool = False

    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_latency_ms: Optional[int] = None

    # Creator action
    creator_action: Optional[Literal["approved", "edited", "rejected", "revised"]] = None
    final_text: Optional[str] = None        # set when creator edits or approves
    sent_at: Optional[datetime] = None
    calendar_event_id: Optional[str] = None
