/**
 * Shared TypeScript types — mirror Pydantic schemas in backend/models/*.
 */

export type Platform = 'instagram' | 'youtube' | 'both';

export type FollowerTier = 'nano' | 'micro' | 'mid' | 'macro' | 'mega';

export type FollowerBucket =
  | 'under_10k'
  | '10k_50k'
  | '50k_200k'
  | '200k_1m'
  | 'over_1m';

export type Niche =
  | 'beauty'
  | 'gaming'
  | 'education'
  | 'finance'
  | 'fashion'
  | 'food'
  | 'tech'
  | 'sports'
  | 'asmr'
  | 'wellness'
  | 'politics'
  | 'gifting';

export interface Creator {
  creator_id: string;
  email: string;
  name: string;
  avatar_url?: string | null;
  onboarding_step: number;
  onboarding_completed_at?: string | null;
  platform_primary?: Platform | null;
  niche?: Niche | null;
  niche_secondary?: string[];
  handle?: string | null;
  follower_tier?: FollowerTier | null;
  follower_count?: number | null;
  geography?: string;
  language_primary?: string;
  gmail_connected?: boolean;
}

export interface ApiError {
  detail?: string;
}
