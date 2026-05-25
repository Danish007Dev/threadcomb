'use client';

import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';

interface StepIndicatorProps {
  currentStep: number; // 1..4
  totalSteps?: number;
}

const STEP_LABELS = ['Platform', 'Niche', 'Profile', 'Connect'];

export function StepIndicator({ currentStep, totalSteps = 4 }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-3 w-full" data-testid="onboarding-step-indicator">
      {Array.from({ length: totalSteps }).map((_, i) => {
        const step = i + 1;
        const isComplete = step < currentStep;
        const isActive = step === currentStep;
        return (
          <div key={step} className="flex items-center gap-3 flex-1">
            <div className="flex items-center gap-2.5">
              <div
                data-testid={`step-dot-${step}`}
                className={cn(
                  'flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium transition-all duration-300',
                  isComplete && 'bg-primary text-primary-foreground',
                  isActive && 'bg-primary text-primary-foreground ring-4 ring-primary/15',
                  !isComplete && !isActive && 'bg-muted text-muted-foreground'
                )}
              >
                {isComplete ? <Check className="w-3.5 h-3.5" /> : step}
              </div>
              <span
                className={cn(
                  'text-xs font-medium tracking-wide uppercase hidden sm:inline',
                  isActive ? 'text-foreground' : 'text-muted-foreground'
                )}
              >
                {STEP_LABELS[i]}
              </span>
            </div>
            {step < totalSteps && (
              <div className="flex-1 h-px bg-border/60 mx-1" aria-hidden="true" />
            )}
          </div>
        );
      })}
    </div>
  );
}
