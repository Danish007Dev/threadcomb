'use client';

/**
 * Zustand store for onboarding state.
 * Persists the working selections in memory across step transitions.
 * Final source of truth is the MongoDB creator document; this store is a UX buffer.
 */

import { create } from 'zustand';
import type { Niche, Platform, FollowerBucket, Creator } from '../lib/types';

interface OnboardingState {
  creator: Creator | null;
  platform: Platform | null;
  primaryNiche: Niche | null;
  secondaryNiches: Niche[];
  handle: string;
  followerBucket: FollowerBucket | null;
  geography: string;
  languagePrimary: string;

  setCreator: (c: Creator | null) => void;
  setPlatform: (p: Platform) => void;
  setPrimaryNiche: (n: Niche | null) => void;
  toggleSecondaryNiche: (n: Niche) => void;
  setHandle: (h: string) => void;
  setFollowerBucket: (b: FollowerBucket) => void;
  setGeography: (g: string) => void;
  setLanguagePrimary: (l: string) => void;
  hydrateFromCreator: (c: Creator) => void;
  reset: () => void;
}

export const useOnboarding = create<OnboardingState>((set, get) => ({
  creator: null,
  platform: null,
  primaryNiche: null,
  secondaryNiches: [],
  handle: '',
  followerBucket: null,
  geography: 'IN',
  languagePrimary: 'en',

  setCreator: (c) => set({ creator: c }),
  setPlatform: (p) => set({ platform: p }),
  setPrimaryNiche: (n) => set({ primaryNiche: n }),
  toggleSecondaryNiche: (n) => {
    const cur = get().secondaryNiches;
    if (cur.includes(n)) {
      set({ secondaryNiches: cur.filter((x) => x !== n) });
    } else if (cur.length < 2) {
      set({ secondaryNiches: [...cur, n] });
    }
  },
  setHandle: (h) => set({ handle: h }),
  setFollowerBucket: (b) => set({ followerBucket: b }),
  setGeography: (g) => set({ geography: g }),
  setLanguagePrimary: (l) => set({ languagePrimary: l }),

  hydrateFromCreator: (c) =>
    set({
      creator: c,
      platform: (c.platform_primary as Platform) || null,
      primaryNiche: (c.niche as Niche) || null,
      secondaryNiches: (c.niche_secondary as Niche[]) || [],
      handle: c.handle || '',
      geography: c.geography || 'IN',
      languagePrimary: c.language_primary || 'en',
    }),

  reset: () =>
    set({
      creator: null,
      platform: null,
      primaryNiche: null,
      secondaryNiches: [],
      handle: '',
      followerBucket: null,
      geography: 'IN',
      languagePrimary: 'en',
    }),
}));
