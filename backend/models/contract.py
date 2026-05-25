"""Contract extraction schema — populated by agents in Session 4."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

from .common import DataClassification


class ContractClause(BaseModel):
    clause_type: str
    raw_text: Optional[str] = None
    risk_score: Optional[float] = None
    risk_label: Optional[str] = None  # low | medium | high


class ContractExtraction(BaseModel):
    creator_id: str
    deal_id: str
    brand_id: str
    gmail_message_id: Optional[str] = None
    clauses: List[ContractClause] = Field(default_factory=list)
    exclusivity_days: Optional[int] = None
    usage_rights_months: Optional[int] = None
    indemnity_present: bool = False
    arbitration_jurisdiction: Optional[str] = None
    overall_risk: Optional[str] = None  # low | medium | high
    extraction_confidence: Optional[float] = None
    requires_human_review: bool = False
    data_classification: DataClassification = Field(default_factory=DataClassification)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
