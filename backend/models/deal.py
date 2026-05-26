"""Deal / Brand / Invoice / SkillsMap / AgentAction / NicheGraph schemas.

Most of these are populated by agents in later sessions. The schemas exist
in Session 1 so that the collections can be created and indexed up-front.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

from .common import DataClassification, DataClassificationTier


# ============================================================================
# Brand
# ============================================================================


class PaymentIntelligence(BaseModel):
    avg_payment_days: Optional[float] = None
    median_payment_days: Optional[float] = None
    payment_reliability: float = 0.5
    total_deals_on_platform: int = 0
    overdue_rate: float = 0.0
    requires_follow_up_rate: float = 0.0
    last_updated: Optional[datetime] = None


class DealIntelligence(BaseModel):
    prefers_content_formats: List[str] = Field(default_factory=list)
    avg_deal_size_inr: Optional[float] = None
    typical_exclusivity_days: Optional[int] = None
    typical_payment_terms: Optional[str] = None
    sends_gifting_before_paid: Optional[bool] = None
    gifting_to_paid_conversion_rate: Optional[float] = None
    active_creator_spend_trend: Optional[str] = None
    last_seen_active_at: Optional[datetime] = None


class Brand(BaseModel):
    name: str
    domain: str
    category: Optional[str] = None
    category_secondary: List[str] = Field(default_factory=list)
    country: str = "IN"
    is_indian_brand: Optional[bool] = None
    is_d2c: Optional[bool] = None
    payment_intelligence: PaymentIntelligence = Field(default_factory=PaymentIntelligence)
    deal_intelligence: DealIntelligence = Field(default_factory=DealIntelligence)
    platform_source: str = "gmail_ingestion"
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    creator_count: int = 0
    data_classification: DataClassification = Field(
        default_factory=lambda: DataClassification(
            tier=DataClassificationTier.ANONYMISABLE,
            anonymisation_eligible=True,
        )
    )


# ============================================================================
# Deal
# ============================================================================


class DealStatus(str, Enum):
    UNANSWERED = "unanswered"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class DealType(str, Enum):
    INSTAGRAM_REEL = "instagram_reel"
    INSTAGRAM_STATIC = "instagram_static"
    INSTAGRAM_STORY = "instagram_story"
    YOUTUBE_DEDICATED = "youtube_dedicated"
    YOUTUBE_INTEGRATION = "youtube_integration"
    YOUTUBE_SHORTS = "youtube_shorts"
    MULTI_PLATFORM = "multi_platform"
    OTHER = "other"


class DealFinancials(BaseModel):
    amount: Optional[float] = None
    amount_raw_text: Optional[str] = None
    amount_ambiguity_flag: bool = False
    currency: str = "INR"
    amount_inr: Optional[float] = None
    payment_terms: Optional[str] = None
    payment_days: Optional[int] = None
    usage_rights_fee: Optional[float] = None


class DealRawSignals(BaseModel):
    exclusivity_mentioned: bool = False
    exclusivity_scope: Optional[str] = None
    exclusivity_duration_days: Optional[int] = None
    deliverables: List[str] = Field(default_factory=list)
    timeline_days: Optional[int] = None
    brand_contact_email: Optional[str] = None
    gmail_thread_id: str
    platform: str = "gmail"


class NegotiationRecord(BaseModel):
    creator_negotiated: bool = False
    rounds: int = 0
    outcome: Optional[str] = None
    rate_change_pct: Optional[float] = None


class Deal(BaseModel):
    creator_id: str
    brand_id: str
    contract_id: Optional[str] = None
    financials: DealFinancials = Field(default_factory=DealFinancials)
    status: DealStatus = DealStatus.UNANSWERED
    deal_type: Optional[DealType] = None
    cluster_label: Optional[str] = None
    raw_signals: DealRawSignals
    negotiation: NegotiationRecord = Field(default_factory=NegotiationRecord)
    extraction_confidence: Optional[float] = None
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    initiated_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    response_time_hrs: Optional[float] = None
    anonymisation_eligible: bool = True
    niche_snapshot: Optional[str] = None
    follower_tier_snapshot: Optional[str] = None
    data_classification: DataClassification = Field(default_factory=DataClassification)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Invoice
# ============================================================================


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PENDING = "pending"
    OVERDUE = "overdue"
    PAID = "paid"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"


class FollowUpRecord(BaseModel):
    count: int = 0
    last_sent_at: Optional[datetime] = None
    next_due_at: Optional[datetime] = None
    tones_used: List[str] = Field(default_factory=list)
    gmail_thread_ids: List[str] = Field(default_factory=list)


class Invoice(BaseModel):
    creator_id: str
    brand_id: str
    deal_id: str
    amount: float
    currency: str = "INR"
    amount_inr: float
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    paid_date: Optional[datetime] = None
    status: InvoiceStatus = InvoiceStatus.PENDING
    days_overdue: int = 0
    payment_days_actual: Optional[int] = None
    follow_ups: FollowUpRecord = Field(default_factory=FollowUpRecord)
    urgency_score: Optional[float] = None
    recommended_tone: Optional[str] = None
    data_classification: DataClassification = Field(default_factory=DataClassification)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Skills Map
# ============================================================================


class SkillsMapType(str, Enum):
    PREFERENCE = "preference"
    SKILL = "skill"
    PATTERN = "pattern"
    BENCHMARK = "benchmark"
    RED_FLAG = "red_flag"


class PreferencePolarity(str, Enum):
    PREFER = "PREFER"
    AVOID = "AVOID"


class SkillsMapPreference(BaseModel):
    polarity: PreferencePolarity
    value: str
    category: str
    strength: float
    effective_strength: float
    inferred_from_deals: List[str] = Field(default_factory=list)


class SkillsMapEvidence(BaseModel):
    count: int = 0
    confidence: float = 0.0
    last_observed: Optional[datetime] = None
    first_observed: Optional[datetime] = None
    decay_rate: float = 0.002


class SkillsMapNode(BaseModel):
    creator_id: str
    type: SkillsMapType
    name: str
    preference: Optional[SkillsMapPreference] = None
    evidence: SkillsMapEvidence = Field(default_factory=SkillsMapEvidence)
    description: str = ""
    niche_specific: bool = False
    anonymisation_eligible: bool = True
    data_classification: DataClassification = Field(
        default_factory=lambda: DataClassification(
            tier=DataClassificationTier.ANONYMISABLE,
            anonymisation_eligible=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Agent Actions (immutable audit log)
# ============================================================================
# AgentActionType / ActionResult moved to models/common.py in Session 2B.
# Re-export here so existing imports `from models.deal import ...` keep working.
from models.common import AgentActionType, ActionResult  # noqa: E402,F401


class AgentAction(BaseModel):
    creator_id: str
    agent: str
    action_type: AgentActionType
    execution: dict = Field(default_factory=dict)
    decision: dict = Field(default_factory=dict)
    outcome: dict = Field(default_factory=dict)
    immutable: bool = True
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_classification: DataClassification = Field(default_factory=DataClassification)


# ============================================================================
# Fan placeholders (Session 5)
# ============================================================================


class FanInteractionPlaceholder(BaseModel):
    creator_id: str
    platform: str
    interaction_type: str
    platform_message_id: str
    received_at: datetime
    data_classification: DataClassification = Field(default_factory=DataClassification)


class FanProfilePlaceholder(BaseModel):
    creator_id: str
    platform_user_id: str
    platform: str
    data_classification: DataClassification = Field(default_factory=DataClassification)


class ResponseTemplate(BaseModel):
    creator_id: str
    trigger_pattern: str
    question_frequency: int = 0
    template_text: str
    creator_approved: bool = False
    approved_at: Optional[datetime] = None
    auto_send_eligible: bool = False
    contains_affiliate_link: bool = False
    contains_brand_mention: bool = False
    times_used: int = 0
    last_used_at: Optional[datetime] = None
    expiry: Optional[datetime] = None
    review_reminder_at: Optional[datetime] = None
    data_classification: DataClassification = Field(default_factory=DataClassification)


# ============================================================================
# Niche Graph (Layer 2 — anonymised intelligence)
# ============================================================================
# NicheGraphNode lives in models/niche_graph.py as of Session 2A.
# Re-exported here for backwards-compatible imports.
from models.niche_graph import NicheGraphNode  # noqa: E402,F401
