'use client';

import { cn } from '../../../lib/utils';

interface BrandScoreBarProps {
  score: number;
  showLabel?: boolean;
  compact?: boolean;
}

export function BrandScoreBar({ score, showLabel = true, compact = false }: BrandScoreBarProps) {
  const pct = Math.round(score * 100);

  let color: string;
  let bgColor: string;
  let label: string;

  if (score < 0.4) {
    color = 'bg-red-500';
    bgColor = 'bg-red-500/10';
    label = 'Poor payer';
  } else if (score < 0.7) {
    color = 'bg-amber-500';
    bgColor = 'bg-amber-500/10';
    label = 'Fair';
  } else {
    color = 'bg-emerald-500';
    bgColor = 'bg-emerald-500/10';
    label = 'Good payer';
  }

  return (
    <div className={cn('space-y-1', compact ? 'max-w-[140px]' : 'max-w-[200px]')}>
      {showLabel && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Payment reliability</span>
          <span className="font-semibold text-foreground">{pct}%</span>
        </div>
      )}
      <div className={cn('h-1.5 rounded-full overflow-hidden', bgColor)}>
        <div
          className={cn('h-full rounded-full transition-all duration-500', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <p className={cn(
          'text-[10px] font-medium tracking-wide uppercase',
          score < 0.4 ? 'text-red-500' : score < 0.7 ? 'text-amber-500' : 'text-emerald-500'
        )}>
          {label}
        </p>
      )}
    </div>
  );
}
