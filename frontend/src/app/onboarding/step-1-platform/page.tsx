'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Instagram, Youtube, Layers, ArrowRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useOnboarding } from '@/store/onboarding';
import { patchStep1 } from '@/lib/api';
import type { Platform } from '@/lib/types';
import { cn } from '@/lib/utils';

const PLATFORMS: Array<{
  id: Platform;
  title: string;
  description: string;
  Icon: React.ComponentType<{ className?: string }>;
  testId: string;
}> = [
  {
    id: 'instagram',
    title: 'Instagram',
    description: 'Brand deals via DMs, Reels, posts and Stories.',
    Icon: Instagram,
    testId: 'platform-card-instagram',
  },
  {
    id: 'youtube',
    title: 'YouTube',
    description: 'Brand integrations and dedicated videos.',
    Icon: Youtube,
    testId: 'platform-card-youtube',
  },
  {
    id: 'both',
    title: 'Both',
    description: 'Instagram and YouTube. You weave on both platforms.',
    Icon: Layers,
    testId: 'platform-card-both',
  },
];

export default function Step1PlatformPage() {
  const router = useRouter();
  const creator = useOnboarding((s) => s.creator);
  const platform = useOnboarding((s) => s.platform);
  const setPlatform = useOnboarding((s) => s.setPlatform);
  const [submitting, setSubmitting] = useState(false);

  const handleNext = async () => {
    if (!platform || !creator) return;
    setSubmitting(true);
    try {
      await patchStep1(creator.creator_id, platform);
      router.push('/onboarding/step-2-niche');
    } catch (err: any) {
      toast.error(err?.message || 'Could not save your selection.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto" data-testid="onboarding-step-1">
      <div className="mb-10">
        <StepIndicator currentStep={1} />
      </div>

      <div className="mb-10">
        <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Step 1 of 4
        </span>
        <h1 className="font-heading text-4xl sm:text-5xl tracking-tight font-medium text-foreground leading-none mt-3">
          Where do your threads live?
        </h1>
        <p className="text-base text-muted-foreground mt-4 max-w-2xl">
          Pick the platform where most of your brand deals happen. You can change this later.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 sm:gap-6">
        {PLATFORMS.map(({ id, title, description, Icon, testId }) => {
          const selected = platform === id;
          return (
            <button
              key={id}
              type="button"
              data-testid={testId}
              onClick={() => setPlatform(id)}
              className={cn(
                'group text-left rounded-xl border bg-card p-7 sm:p-8 transition-all duration-300',
                'hover:-translate-y-0.5 hover:shadow-lift',
                selected
                  ? 'border-primary ring-2 ring-primary/15 shadow-elevated'
                  : 'border-border/50 hover:border-primary/40'
              )}
            >
              <div
                className={cn(
                  'w-11 h-11 rounded-lg flex items-center justify-center mb-5 transition-colors',
                  selected ? 'bg-primary text-primary-foreground' : 'bg-accent text-accent-foreground'
                )}
              >
                <Icon className="w-5 h-5" />
              </div>
              <h3 className="font-heading text-xl font-medium text-foreground">{title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed mt-2">
                {description}
              </p>
              <div
                className={cn(
                  'mt-6 inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide',
                  selected ? 'text-primary' : 'text-muted-foreground'
                )}
              >
                {selected ? 'Selected' : 'Choose'}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-12 flex items-center justify-between">
        <p className="text-xs text-muted-foreground tracking-wide">
          Your selection is saved before you move on.
        </p>
        <Button
          onClick={handleNext}
          disabled={!platform || submitting}
          size="lg"
          data-testid="step-1-next-btn"
        >
          Continue
          <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
