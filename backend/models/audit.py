"""Audit Report models — SynthesisContext, AuditFinding, SynthesisReport.

Used by the Gemini Pro synthesis call (Session 3).
"""

from pydantic import BaseModel
from typing import Optional, List, Dict


class SynthesisContext(BaseModel):
    """Typed context passed to Gemini Pro for Audit Report synthesis."""
    creator_id: str
    creator_niche: str
    creator_follower_tier: str
    creator_handle: Optional[str] = None

    # From Pipeline 1
    unanswered_deal_count: int
    unanswered_value_typical: float
    unanswered_value_min: float
    unanswered_value_max: float
    has_financial_estimates: bool

    # From Pipeline 2
    payment_reliability_data: List[Dict]

    # From Pipeline 3
    rate_gap_data: Dict

    # Totals
    total_deals_found: int
    total_deals_extracted: int
    total_confidence_below_threshold: int  # went to HITL

    # Skills Map signals
    confirmed_preferences: List[Dict]      # preferences with confidence > 0.7


class AuditFinding(BaseModel):
    """A single finding in the Audit Report."""
    section: str           # "revenue_leakage" | "payment_risk" | "rate_gap" | "operational_dna"
    title: str
    severity: str          # "high" | "medium" | "low" | "positive"
    finding_text: str      # what was found — plain language
    evidence: str          # what data supports this — cite specific numbers or counts
    recommendation: str    # what the creator should do about it
    value_inr: Optional[float] = None   # monetary value if applicable — None if unknown
    value_unknown: bool = False         # True if finding has monetary impact but amount unclear
    # RULE: If value is unknown, say "Unknown — amount not stated in emails"
    # NEVER fabricate a rupee amount. Never use "approximately" without a cited basis.


class SynthesisReport(BaseModel):
    """Output from Gemini Pro synthesis."""
    findings: List[AuditFinding]
    executive_summary: str              # 2–3 sentences, plain language
    total_recoverable_value: Optional[float] = None   # None if no non-ambiguous amounts
    total_recoverable_unknown: bool = False            # True if there are unanswered deals with unknown value
    skills_map_summary: str            # what ThreadComb learned about how this creator operates
    data_quality_note: Optional[str] = None   # honest note if data was limited or confidence was low
