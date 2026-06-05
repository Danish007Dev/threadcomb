'use client';

import { cn } from '../../lib/utils';

interface ThreadCombLogoProps {
  className?: string;
  showWordmark?: boolean;
  size?: number;
}

/**
 * ThreadComb logo — user's custom Hexagon envelope SVG.
 */
export function ThreadCombLogo({
  className,
  showWordmark = true,
  size = 32,
}: ThreadCombLogoProps) {
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)} data-testid="threadcomb-logo">
      <svg
        width={size}
        height={size}
        viewBox="-75 -65 150 130"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <polygon points="-30,-52 30,-52 60,0 30,52 -30,52 -60,0" fill="#C4553A"/>
        <polygon points="-30,-52 30,-52 55.4,-8 0,14 -55.4,-8" fill="#F5A623"/>
        <line x1="-55.4" y1="-8" x2="0" y2="14" stroke="#9C3E1A" strokeWidth="1.5" opacity="0.4"/>
        <line x1="55.4" y1="-8" x2="0" y2="14" stroke="#9C3E1A" strokeWidth="1.5" opacity="0.4"/>
        <polygon points="-30,-52 30,-52 60,0 30,52 -30,52 -60,0" fill="none" strokeWidth="5" strokeLinejoin="round" className="stroke-[#C85C00] dark:stroke-[#F5A623] transition-colors"/>
      </svg>
      {showWordmark && (
        <span className="font-mono text-xl font-bold tracking-tighter text-foreground">
          ThreadComb
        </span>
      )}
    </div>
  );
}

