'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getMe } from '@/lib/api';
import { useOnboarding } from '@/store/onboarding';
import { ThreadCombLogo } from '@/components/brand/Logo';

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const setCreator = useOnboarding((s) => s.setCreator);
  const hydrate = useOnboarding((s) => s.hydrateFromCreator);
  const creator = useOnboarding((s) => s.creator);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (creator) {
      setChecked(true);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) {
          setCreator(me);
          hydrate(me);
          setChecked(true);
        }
      } catch {
        if (!cancelled) router.replace('/login');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [creator, router, setCreator, hydrate]);

  if (!checked) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background tc-grain" data-testid="onboarding-layout">
      <header className="px-6 md:px-10 py-6 border-b border-border/40 bg-background/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <ThreadCombLogo className="text-primary" data-testid="onboarding-logo" />
          <span className="text-xs text-muted-foreground tracking-wider uppercase hidden sm:inline">
            Setting up your ThreadComb
          </span>
        </div>
      </header>
      <main className="px-6 md:px-10 py-10 md:py-14">{children}</main>
    </div>
  );
}
