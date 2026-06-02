from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class InvoiceFollowUpDraft(BaseModel):
    """A single follow-up draft for one overdue invoice."""
    invoice_id: str
    deal_id: Optional[str] = None
    creator_id: str
    brand_name: Optional[str] = None
    brand_domain: Optional[str] = None
    amount_inr: Optional[float] = None
    days_overdue: int
    urgency_score: float
    recommended_tone: Literal["gentle", "firm", "final_notice"]
    follow_up_count: int                     # how many previous follow-ups have been sent
    draft_text: str
    voice_compliance_score: float
    model_used: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    # Creator action
    creator_action: Optional[Literal["approved", "skipped"]] = None
    sent_at: Optional[datetime] = None
    data_classification: dict = Field(default_factory=lambda: {
        "tier": "personal_identifiable",
        "deletion_policy": "on_request_30d",
        "export_eligible": True,
    })


class BatchFollowUpResult(BaseModel):
    """Complete output of one Revenue Guardian run."""
    creator_id: str
    run_date: datetime = Field(default_factory=datetime.utcnow)
    total_overdue: int
    total_drafted: int
    total_sent: int
    total_skipped: int
    total_recovered_inr: float              # filled as invoices get paid
    drafts: List[InvoiceFollowUpDraft] = []
