'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { exchangeSession } from '@/lib/api';
import { ThreadCombLogo } from '@/components/brand/Logo';

/**
 * AuthCallback — runs at /auth/callback after Emergent Auth redirect.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH.
 *
 * Reads #session_id from the URL fragment, calls our backend /api/auth/session
 * (which exchanges it via Emergent's session-data endpoint), then routes to
 * the correct onboarding step or /dashboard.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      router.replace('/login');
      return;
    }
    const sessionId = decodeURIComponent(match[1]);

    (async () => {
      try {
        const { creator } = await exchangeSession(sessionId);
        // Clear the URL fragment for cleanliness
        if (typeof window !== 'undefined') {
          window.history.replaceState(null, '', '/auth/callback');
        }
        const step = creator.onboarding_step ?? 0;
        if (step >= 5) router.replace('/dashboard');
        else if (step === 0) router.replace('/onboarding/step-1-platform');
        else if (step === 1) router.replace('/onboarding/step-2-niche');
        else if (step === 2) router.replace('/onboarding/step-3-profile');
        else router.replace('/onboarding/step-4-connect');
      } catch (err) {
        toast.error('Could not complete sign-in. Please try again.');
        router.replace('/login');
      }
    })();
  }, [router]);

  return (
    <div className="min-h-dvh flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-5" data-testid="auth-callback">
        <ThreadCombLogo showWordmark={false} size={40} className="text-primary" />
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
        <p className="text-sm text-muted-foreground tracking-wide uppercase">
          Signing you in
        </p>
      </div>
    </div>
  );
}
