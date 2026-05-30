'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { getMe } from '../../../lib/api';
import { ThreadCombLogo } from '../../../components/brand/Logo';

/**
 * AuthCallback — runs after Google OAuth redirect.
 *
 * The backend has already set the session cookie, so this page only resolves
 * the creator state and routes accordingly.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    (async () => {
      try {
        const creator = await getMe();
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
