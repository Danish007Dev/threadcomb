'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Handshake, Eye, Wand2, Loader2 } from 'lucide-react';
import { getInboundDeals } from '../../../lib/api';
import type { InboundDeal } from '../../../lib/api';

interface DealsSummaryWidgetProps {
  creatorId: string;
}

export function DealsSummaryWidget({ creatorId }: DealsSummaryWidgetProps) {
  const router = useRouter();
  const [deals, setDeals] = useState<InboundDeal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getInboundDeals();
        if (!cancelled) setDeals(data);
      } catch {
        // Silently ignore — widget is supplemental
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [creatorId]);

  if (loading) {
    return (
      <div className="tc-card p-5 flex items-center gap-3">
        <Loader2 className="w-4 h-4 animate-spin text-primary" />
        <span className="text-sm text-muted-foreground">Checking for deals...</span>
      </div>
    );
  }

  if (deals.length === 0) return null;

  const pendingDrafts = deals.filter(d => d.has_pending_draft).length;
  const unanswered = deals.filter(d => !d.has_pending_draft).length;

  return (
    <div className="tc-card p-5 md:p-6" data-testid="deals-summary-widget">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
            <Handshake className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-medium text-foreground text-sm">Deals Needing Attention</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {pendingDrafts > 0 && (
                <span className="text-primary font-semibold">{pendingDrafts} draft{pendingDrafts > 1 ? 's' : ''} waiting</span>
              )}
              {pendingDrafts > 0 && unanswered > 0 && ' · '}
              {unanswered > 0 && (
                <span>{unanswered} unanswered</span>
              )}
            </p>
          </div>
        </div>

        <button
          onClick={() => router.push('/dashboard/deals')}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity shadow-sm"
          data-testid="deals-review-btn"
        >
          <Eye className="w-3.5 h-3.5" />
          Review
        </button>
      </div>
    </div>
  );
}
