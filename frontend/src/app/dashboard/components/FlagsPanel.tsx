'use client';

import { AlertTriangle, Info, TrendingUp } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { DraftFlag } from '../../../lib/api';

const SEVERITY_STYLES: Record<string, { border: string; bg: string; text: string; Icon: typeof AlertTriangle }> = {
  high: {
    border: 'border-red-300 dark:border-red-800',
    bg: 'bg-red-50 dark:bg-red-950/30',
    text: 'text-red-700 dark:text-red-400',
    Icon: AlertTriangle,
  },
  medium: {
    border: 'border-amber-300 dark:border-amber-800',
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    text: 'text-amber-700 dark:text-amber-400',
    Icon: AlertTriangle,
  },
  low: {
    border: 'border-blue-200 dark:border-blue-800',
    bg: 'bg-blue-50 dark:bg-blue-950/20',
    text: 'text-blue-600 dark:text-blue-400',
    Icon: Info,
  },
};

interface FlagsPanelProps {
  flags: DraftFlag[];
  compact?: boolean;
}

export function FlagsPanel({ flags, compact = false }: FlagsPanelProps) {
  if (!flags.length) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Flags ({flags.length})
      </p>
      <div className="space-y-1.5">
        {flags.map((flag, i) => {
          const style = SEVERITY_STYLES[flag.severity] || SEVERITY_STYLES.low;
          const FlagIcon = style.Icon;
          return (
            <div
              key={i}
              className={cn(
                'rounded-lg border p-3 transition-colors',
                style.border,
                style.bg,
              )}
            >
              <div className="flex items-start gap-2">
                <FlagIcon className={cn('w-3.5 h-3.5 mt-0.5 shrink-0', style.text)} />
                <div className="flex-1 min-w-0 space-y-0.5">
                  <p className={cn('text-xs font-medium leading-snug', style.text)}>
                    {flag.message}
                  </p>
                  {!compact && flag.recommended_action && (
                    <p className="text-[10px] text-muted-foreground leading-snug">
                      → {flag.recommended_action}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
