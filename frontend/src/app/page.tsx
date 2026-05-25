'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getMe } from '@/lib/api';

/**
 * Root entry. Decides where the user lands:
 *  - URL contains #session_id=... -> route to /auth/callback (handles exchange)
 *  - Has valid session_token cookie -> /dashboard or onboarding step they're on
 *  - Otherwise -> /login
 */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    // CRITICAL: If returning from OAuth callback, do NOT call /auth/me — let
    // the callback page exchange the session_id first.
    if (typeof window !== 'undefined' && window.location.hash?.includes('session_id=')) {
      router.replace(`/auth/callback${window.location.hash}`);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (cancelled) return;
        if ((me.onboarding_step ?? 0) >= 5) {
          router.replace('/dashboard');
        } else if (me.onboarding_step === 0) {
          router.replace('/onboarding/step-1-platform');
        } else if (me.onboarding_step === 1) {
          router.replace('/onboarding/step-2-niche');
        } else if (me.onboarding_step === 2) {
          router.replace('/onboarding/step-3-profile');
        } else {
          router.replace('/onboarding/step-4-connect');
        }
      } catch {
        if (!cancelled) router.replace('/login');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="min-h-dvh flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4" data-testid="root-loading">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        <p className="text-sm text-muted-foreground tracking-wide uppercase">Loading ThreadComb</p>
      </div>
    </div>
  );
}
