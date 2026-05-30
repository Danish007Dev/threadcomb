'use client';

import { cn } from '../../lib/utils';

interface ThreadCombLogoProps {
  className?: string;
  showWordmark?: boolean;
  size?: number;
}

/**
 * ThreadComb logo — a stylised comb with woven threads.
 * Pure SVG so it scales crisply and inherits the primary color.
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
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {/* Comb back */}
        <rect
          x="4"
          y="6"
          width="24"
          height="6"
          rx="2"
          stroke="currentColor"
          strokeWidth="2"
          fill="hsl(var(--accent))"
        />
        {/* Comb teeth */}
        {[8, 12, 16, 20, 24].map((cx) => (
          <line
            key={cx}
            x1={cx}
            y1="12"
            x2={cx}
            y2="22"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        ))}
        {/* Thread weaving through teeth */}
        <path
          d="M6 26 C 10 18, 14 30, 18 22 S 26 28, 28 22"
          stroke="hsl(var(--terracotta))"
          strokeWidth="1.8"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      {showWordmark && (
        <span className="font-heading text-lg font-semibold tracking-tight text-foreground">
          ThreadComb
        </span>
      )}
    </div>
  );
}
