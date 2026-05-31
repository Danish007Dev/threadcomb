"""Deal / Brand / Invoice / SkillsMap / AgentAction / NicheGraph schemas.

Most of these are populated by agents in later sessions. The schemas exist
in Session 1 so that the collections can be created and indexed up-front.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone
from enum import Enum

from .common import DataClassification, DataClassificationTier


# ============================================================================
# Gemini Extraction Schemas (Session 3)
# These are flat schemas for Gemini structured output — NOT MongoDB documents.
# The extraction worker maps these into the Deal/Brand document structures.
# ============================================================================


class DealExtraction(BaseModel):
    """
    Output schema for Gemini Flash extraction of a single brand deal email thread.
    Used with response_mime_type='application/json' and response_schema=DealExtraction.
    Every field has a default — extraction must never fail due to missing fields.
    """

    # Brand identification
    brand_name: Optional[str] = None
    brand_domain: Optional[str] = None          # extracted from sender email if not stated
    brand_category: Optional[str] = None         # beauty | gaming | edtech | fintech | fashion | fmcg | tech | food | sports | wellness | other

    # Deal type
    deal_type: Optional[Literal[
        "instagram_reel", "instagram_post", "instagram_story",
        "youtube_dedicated", "youtube_integration", "youtube_shorts",
        "multi_platform", "other"
    ]] = None

    # Financial signals
    amount_raw_text: Optional[str] = None        # exact text from email mentioning money
    amount_ambiguity_flag: bool = False          # True if amount is informal/unclear
    amount_min: Optional[float] = None          # None if ambiguous
    amount_max: Optional[float] = None          # None if ambiguous
    amount_typical: Optional[float] = None      # best single estimate if stated
    currency: str = "INR"

    # CRITICAL RULE: If amount_ambiguity_flag is True,
    # amount_min, amount_max, and amount_typical MUST all be None.
    # Never auto-populate financial fields when the amount is unclear.
    # Examples that trigger ambiguity flag:
    # "50 hazaar", "do lakh", "let's discuss rates", "competitive budget",
    # "as per your rate card", any non-numeric expression

    # Contract signals
    exclusivity_mentioned: bool = False
    exclusivity_scope: Optional[str] = None     # "instagram only", "all platforms", etc.
    exclusivity_duration_days: Optional[int] = None
    payment_terms_mentioned: Optional[str] = None  # "NET-30", "50% upfront", etc.
    payment_days: Optional[int] = None
    deliverables: List[str] = []                # ["1 Reel", "3 Stories", "1 YouTube integration"]
    timeline_days: Optional[int] = None         # days to deliver after acceptance

    # Deal status
    deal_status: Literal[
        "unanswered",    # creator never replied
        "negotiating",   # back and forth in progress
        "accepted",      # deal confirmed
        "rejected",      # creator or brand declined
        "delivered",     # content posted
        "invoiced",      # invoice sent
        "paid",          # payment received
        "overdue",       # payment past due
        "cancelled"      # deal fell through
    ] = "unanswered"

    negotiation_state: Optional[Literal[
        "initial_inquiry", "counter_sent", "counter_received",
        "terms_agreed", "contract_sent", "signed"
    ]] = None

    # Sender metadata
    brand_contact_email: Optional[str] = None
    is_agency_contact: bool = False             # True if an agency is reaching out on behalf of brand
    gmail_thread_id: str = ""

    # Response timing
    creator_response_time_hrs: Optional[float] = None   # hours between first email and creator reply
    thread_unanswered: bool = False             # True if creator never replied to this thread

    # Extraction quality
    extraction_confidence: float = 0.0         # 0.0–1.0: model's confidence in this extraction
    requires_human_review: bool = False
    review_reason: Optional[str] = None        # why human review is needed

    # Hindi/mixed language flag
    hindi_mode: bool = False                   # True if email contains Hindi content
    language: str = "en"

    # Email metadata
    sender_email: str = ""
    subject: str = ""
    date_sent: Optional[str] = None            # ISO string from email header


class ContractExtraction(BaseModel):
    """
    Output schema for extracting structured data from a PDF contract attachment.
    Used separately from DealExtraction — runs only on PDF attachments in deal threads.
    """
    payment_days: Optional[int] = None
    payment_structure: Optional[str] = None    # "upfront", "milestone", "net-30", etc.
    exclusivity_scope: Optional[str] = None
    exclusivity_duration_days: Optional[int] = None
    ip_ownership: Optional[Literal["creator_retains", "brand_acquires", "shared", "not_stated"]] = None
    kill_fee_present: bool = False
    kill_fee_percentage: Optional[float] = None
    revision_limit: Optional[int] = None
    usage_rights_duration_days: Optional[int] = None
    content_approval_required: bool = False
    morality_clause_present: bool = False
    overall_risk_score: float = 0.0            # 1.0 (creator-friendly) to 5.0 (brand-heavy)
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    extraction_confidence: float = 0.0


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
    embedding_vector: Optional[List[float]] = None
    embedding_model: Optional[str] = None
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
