'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  Brush,
  Gamepad2,
  GraduationCap,
  Landmark,
  Shirt,
  UtensilsCrossed,
  Cpu,
  Trophy,
  Headphones,
  Heart,
  Gift,
  Newspaper,
  ArrowLeft,
  ArrowRight,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useOnboarding } from '@/store/onboarding';
import { patchStep2 } from '@/lib/api';
import type { Niche } from '@/lib/types';
import { cn } from '@/lib/utils';

const NICHES: Array<{ id: Niche; label: string; Icon: React.ComponentType<{ className?: string }>; testId: string }> = [
  { id: 'beauty', label: 'Beauty', Icon: Brush, testId: 'niche-item-beauty' },
  { id: 'gaming', label: 'Gaming', Icon: Gamepad2, testId: 'niche-item-gaming' },
  { id: 'education', label: 'Education', Icon: GraduationCap, testId: 'niche-item-education' },
  { id: 'finance', label: 'Finance', Icon: Landmark, testId: 'niche-item-finance' },
  { id: 'fashion', label: 'Fashion', Icon: Shirt, testId: 'niche-item-fashion' },
  { id: 'food', label: 'Food', Icon: UtensilsCrossed, testId: 'niche-item-food' },
  { id: 'tech', label: 'Tech', Icon: Cpu, testId: 'niche-item-tech' },
  { id: 'sports', label: 'Sports', Icon: Trophy, testId: 'niche-item-sports' },
  { id: 'asmr', label: 'ASMR', Icon: Headphones, testId: 'niche-item-asmr' },
  { id: 'wellness', label: 'Wellness', Icon: Heart, testId: 'niche-item-wellness' },
  { id: 'gifting', label: 'PR / Gifting', Icon: Gift, testId: 'niche-item-gifting' },
  { id: 'politics', label: 'Politics / News', Icon: Newspaper, testId: 'niche-item-politics' },
];

export default function Step2NichePage() {
  const router = useRouter();
  const creator = useOnboarding((s) => s.creator);
  const primaryNiche = useOnboarding((s) => s.primaryNiche);
  const secondaryNiches = useOnboarding((s) => s.secondaryNiches);
  const setPrimary = useOnboarding((s) => s.setPrimaryNiche);
  const toggleSecondary = useOnboarding((s) => s.toggleSecondaryNiche);
  const [submitting, setSubmitting] = useState(false);

  const handleSelect = (niche: Niche) => {
    if (!primaryNiche) {
      setPrimary(niche);
      return;
    }
    if (primaryNiche === niche) {
      // tap primary again to reset to nothing — feels natural
      setPrimary(null);
      return;
    }
    toggleSecondary(niche);
  };

  const handleNext = async () => {
    if (!primaryNiche || !creator) return;
    setSubmitting(true);
    try {
      await patchStep2(creator.creator_id, primaryNiche, secondaryNiches);
      router.push('/onboarding/step-3-profile');
    } catch (err: any) {
      toast.error(err?.message || 'Could not save your niches.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto" data-testid="onboarding-step-2">
      <div className="mb-10">
        <StepIndicator currentStep={2} />
      </div>

      <div className="mb-10">
        <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Step 2 of 4
        </span>
        <h1 className="font-heading text-4xl sm:text-5xl tracking-tight font-medium text-foreground leading-none mt-3">
          What is your creative DNA?
        </h1>
        <p className="text-base text-muted-foreground mt-4 max-w-2xl">
          Pick your primary niche first. Then add up to 2 secondary niches you also create in.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 sm:gap-4" data-testid="niche-grid">
        {NICHES.map(({ id, label, Icon, testId }) => {
          const isPrimary = primaryNiche === id;
          const isSecondary = secondaryNiches.includes(id);
          return (
            <button
              key={id}
              type="button"
              data-testid={testId}
              onClick={() => handleSelect(id)}
              className={cn(
                'group flex flex-col items-start gap-3 text-left rounded-xl border bg-card p-5 transition-all duration-300',
                'hover:-translate-y-0.5 hover:shadow-elevated',
                isPrimary && 'border-primary bg-primary text-primary-foreground shadow-elevated',
                !isPrimary && isSecondary && 'border-primary ring-2 ring-primary/15',
                !isPrimary && !isSecondary && 'border-border/50 hover:border-primary/40'
              )}
            >
              <div
                className={cn(
                  'w-9 h-9 rounded-lg flex items-center justify-center transition-colors',
                  isPrimary
                    ? 'bg-primary-foreground/15 text-primary-foreground'
                    : isSecondary
                    ? 'bg-primary/10 text-primary'
                    : 'bg-accent text-accent-foreground'
                )}
              >
                <Icon className="w-4 h-4" />
              </div>
              <span className={cn('text-sm font-medium', isPrimary ? 'text-primary-foreground' : 'text-foreground')}>
                {label}
              </span>
              <span
                className={cn(
                  'text-[10px] font-medium uppercase tracking-[0.14em]',
                  isPrimary && 'text-primary-foreground/80',
                  !isPrimary && isSecondary && 'text-primary',
                  !isPrimary && !isSecondary && 'text-muted-foreground'
                )}
              >
                {isPrimary ? 'Primary' : isSecondary ? 'Secondary' : 'Tap to select'}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-10 flex items-center justify-between flex-wrap gap-4">
        <Button
          variant="ghost"
          onClick={() => router.push('/onboarding/step-1-platform')}
          data-testid="step-2-back-btn"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <div className="flex items-center gap-4">
          <span className="text-xs text-muted-foreground hidden sm:inline">
            {primaryNiche ? `Primary set · ${secondaryNiches.length} secondary` : 'Pick a primary niche'}
          </span>
          <Button
            onClick={handleNext}
            disabled={!primaryNiche || submitting}
            size="lg"
            data-testid="step-2-next-btn"
          >
            Continue
            <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
