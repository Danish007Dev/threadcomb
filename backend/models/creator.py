"""Creator collection schema — primary document for each ThreadComb user."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

from .common import DataClassification, DataClassificationTier


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    BOTH = "both"


class FollowerTier(str, Enum):
    NANO = "nano"  # < 10K
    MICRO = "micro"  # 10K–50K
    MID = "mid"  # 50K–200K
    MACRO = "macro"  # 200K–1M
    MEGA = "mega"  # 1M+


class Niche(str, Enum):
    BEAUTY = "beauty"
    GAMING = "gaming"
    EDUCATION = "education"
    FINANCE = "finance"
    FASHION = "fashion"
    FOOD = "food"
    TECH = "tech"
    SPORTS = "sports"
    ASMR = "asmr"
    WELLNESS = "wellness"
    POLITICS = "politics"
    GIFTING = "gifting"


class Plan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class RateBand(BaseModel):
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None


class RateBenchmarks(BaseModel):
    instagram_reel: RateBand = Field(default_factory=RateBand)
    instagram_static: RateBand = Field(default_factory=RateBand)
    instagram_story: RateBand = Field(default_factory=RateBand)
    youtube_dedicated: RateBand = Field(default_factory=RateBand)
    youtube_integration: RateBand = Field(default_factory=RateBand)
    youtube_shorts: RateBand = Field(default_factory=RateBand)
    currency: str = "INR"


class VoiceProfileBrand(BaseModel):
    """Extracted from outbound BRAND DEAL emails only — formal register."""

    avg_sentence_length: Optional[float] = None
    formality_score: Optional[float] = None
    formality_label: Optional[str] = None
    emoji_frequency: Optional[float] = None
    top_emojis: List[str] = Field(default_factory=list)
    common_openers: List[str] = Field(default_factory=list)
    common_closers: List[str] = Field(default_factory=list)
    uses_caps_emphasis: Optional[bool] = None
    avg_response_length: Optional[int] = None
    hindi_english_ratio: Optional[float] = None
    last_calibrated_at: Optional[datetime] = None
    calibration_sample_count: int = 0


class VoiceProfileFan(BaseModel):
    """Extracted from outbound FAN REPLY emails/comments — casual register."""

    avg_sentence_length: Optional[float] = None
    formality_score: Optional[float] = None
    emoji_frequency: Optional[float] = None
    top_emojis: List[str] = Field(default_factory=list)
    common_openers: List[str] = Field(default_factory=list)
    uses_hindi_affirmations: Optional[bool] = None
    last_calibrated_at: Optional[datetime] = None


class GmailWatch(BaseModel):
    history_id: Optional[str] = None
    expiry: Optional[datetime] = None
    topic_name: Optional[str] = None
    active: bool = False


class Subscription(BaseModel):
    plan: Plan = Plan.FREE
    status: str = "active"
    started_at: Optional[datetime] = None
    pilot_started_at: Optional[datetime] = None
    pilot_expires_at: Optional[datetime] = None


class Creator(BaseModel):
    # Identity
    creator_id: str  # custom UUID, indexed (avoids _id issues)
    google_sub: Optional[str] = None  # Google OAuth subject ID — unique, indexed
    email: str  # indexed, unique
    name: str
    avatar_url: Optional[str] = None

    # Creator profile
    handle: Optional[str] = None
    platform_primary: Optional[Platform] = None
    follower_count: Optional[int] = None
    follower_tier: Optional[FollowerTier] = None
    niche: Optional[Niche] = None
    niche_secondary: List[str] = Field(default_factory=list)
    geography: str = "IN"
    language_primary: str = "en"

    # Onboarding state
    onboarding_step: int = 0
    onboarding_completed_at: Optional[datetime] = None

    # Knowledge graph
    voice_profile_brand: VoiceProfileBrand = Field(default_factory=VoiceProfileBrand)
    voice_profile_fan: VoiceProfileFan = Field(default_factory=VoiceProfileFan)
    rate_benchmarks: RateBenchmarks = Field(default_factory=RateBenchmarks)
    skills_map_version: int = 0
    last_synthesis_at: Optional[datetime] = None

    # Gmail
    gmail_connected: bool = False
    gmail_watch: GmailWatch = Field(default_factory=GmailWatch)
    gmail_secret_path: Optional[str] = None

    # Subscription
    subscription: Subscription = Field(default_factory=Subscription)

    # Compliance
    data_classification: DataClassification = Field(default_factory=DataClassification)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Onboarding step input payloads
class Step1Input(BaseModel):
    platform: Platform


class Step2Input(BaseModel):
    niche: Niche
    niche_secondary: List[str] = Field(default_factory=list)


class FollowerBucket(str, Enum):
    UNDER_10K = "under_10k"
    K_10_50 = "10k_50k"
    K_50_200 = "50k_200k"
    K_200_1M = "200k_1m"
    OVER_1M = "over_1m"


def follower_bucket_to_tier(bucket: FollowerBucket) -> FollowerTier:
    mapping = {
        FollowerBucket.UNDER_10K: FollowerTier.NANO,
        FollowerBucket.K_10_50: FollowerTier.MICRO,
        FollowerBucket.K_50_200: FollowerTier.MID,
        FollowerBucket.K_200_1M: FollowerTier.MACRO,
        FollowerBucket.OVER_1M: FollowerTier.MEGA,
    }
    return mapping[bucket]


class Step3Input(BaseModel):
    handle: Optional[str] = None
    follower_bucket: FollowerBucket
    geography: str = "IN"
    language_primary: str = "en"


class CreatorCreateInput(BaseModel):
    google_sub: Optional[str] = None
    email: str
    name: str
    avatar_url: Optional[str] = None
