'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Handshake, Loader2, PenTool, CheckCircle, Clock } from 'lucide-react';
import { getInboundDeals } from '../../../lib/api';
import type { InboundDeal } from '../../../lib/api';
import { useIngestionStatus } from '../../../hooks/useIngestionStatus';

export function DealPipelineWidget({ creatorId }: { creatorId?: string }) {
  const router = useRouter();
  const [deals, setDeals] = useState<InboundDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const { events } = useIngestionStatus(creatorId);

  const fetchDeals = async () => {
    try {
      const data = await getInboundDeals();
      setDeals(data);
    } catch {
      // Silently ignore
    }
  };

  // Auto-hide toast
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // Listen for realtime deals
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[events.length - 1];
    if (latest.event === 'new_deal_detected') {
      setToast({ message: latest.message || 'New brand deal detected! Extracting...', type: 'info' });
      // We don't fetchDeals here yet, because the deal hasn't been saved to DB.
    } else if (latest.event === 'extraction_complete') {
      setToast({ message: latest.message || 'Brand details extracted. Generating reply draft...', type: 'info' });
      fetchDeals(); // Now it exists in the DB, it will show as Unanswered
    } else if (latest.event === 'draft_ready') {
      setToast({ message: latest.message || 'New reply draft is ready.', type: 'success' });
      fetchDeals(); // Now it has a draft, it moves to Pending Approval
    }
  }, [events]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getInboundDeals();
        if (!cancelled) setDeals(data);
      } catch {
        // Silently ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="tc-card p-6 flex items-center justify-center min-h-[160px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const unanswered = deals.filter(d => !d.has_pending_draft && d.status === 'unanswered');
  const pending = deals.filter(d => d.has_pending_draft);
  const negotiating = deals.filter(d => d.status === 'negotiating');

  return (
    <div className="tc-card p-6" data-testid="deal-pipeline-widget">
      <div className="flex items-center gap-3 mb-6">
        <Handshake className="w-5 h-5 text-primary" />
        <h3 className="font-medium text-lg text-foreground">Deal Pipeline</h3>
      </div>

      {toast && (
        <div className={`mb-4 p-3 rounded-lg text-sm font-medium border ${
          toast.type === 'success' 
            ? 'bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-400' 
            : 'bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-950/30 dark:border-blue-800 dark:text-blue-400'
        }`}>
          {toast.message}
        </div>
      )}
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Unanswered */}
        <div className="bg-slate-50 dark:bg-card/40 rounded-xl p-4 border border-slate-100 dark:border-border/60">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Unanswered</span>
            <span className="bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 text-xs font-semibold px-2 py-1 rounded-full">
              {unanswered.length}
            </span>
          </div>
          {unanswered.map((deal) => (
            <div key={deal._id} className="bg-white dark:bg-card p-3 rounded-lg border border-slate-200 dark:border-border mb-2 shadow-sm dark:shadow-none">
              <p className="text-sm font-medium text-foreground">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <button
                onClick={() => router.push('/dashboard/deals')}
                className="w-full inline-flex justify-center items-center gap-2 bg-slate-100 dark:bg-accent/50 hover:bg-slate-200 dark:hover:bg-accent text-slate-700 dark:text-slate-200 text-xs px-3 py-1.5 rounded transition-colors"
              >
                <PenTool className="w-3.5 h-3.5" /> Generate Draft
              </button>
            </div>
          ))}
          {unanswered.length === 0 && (
             <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-2">No unanswered deals.</p>
          )}
        </div>

        {/* Drafts Pending Approval */}
        <div className="bg-slate-50 dark:bg-card/40 rounded-xl p-4 border border-slate-100 dark:border-border/60">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Pending Approval</span>
            <span className="bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 text-xs font-semibold px-2 py-1 rounded-full">
              {pending.length}
            </span>
          </div>
          {pending.map((deal) => (
            <div key={deal._id} className="bg-white dark:bg-card p-3 rounded-lg border border-amber-200 dark:border-amber-900/50 mb-2 shadow-sm dark:shadow-none border-l-2 border-l-amber-500 dark:border-l-amber-500">
              <p className="text-sm font-medium text-foreground">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <button
                onClick={() => router.push('/dashboard/deals')}
                className="w-full inline-flex justify-center items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white text-xs px-3 py-1.5 rounded transition-colors"
              >
                <CheckCircle className="w-3.5 h-3.5" /> Review Draft
              </button>
            </div>
          ))}
          {pending.length === 0 && (
             <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-2">No drafts to review.</p>
          )}
        </div>

        {/* In Negotiation */}
        <div className="bg-slate-50 dark:bg-card/40 rounded-xl p-4 border border-slate-100 dark:border-border/60">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">In Negotiation</span>
            <span className="bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 text-xs font-semibold px-2 py-1 rounded-full">
              {negotiating.length}
            </span>
          </div>
          {negotiating.map((deal) => (
            <div key={deal._id} className="bg-white dark:bg-card p-3 rounded-lg border border-slate-200 dark:border-border mb-2 shadow-sm dark:shadow-none">
              <p className="text-sm font-medium text-foreground">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <div className="inline-flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-2 py-1 rounded">
                <Clock className="w-3.5 h-3.5" /> Awaiting Response
              </div>
            </div>
          ))}
          {negotiating.length === 0 && (
             <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-2">No active negotiations.</p>
          )}
        </div>
      </div>
    </div>
  );
}
