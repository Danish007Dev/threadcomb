'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Handshake, Loader2, PenTool, CheckCircle, Clock } from 'lucide-react';
import { getInboundDeals } from '../../../lib/api';
import type { InboundDeal } from '../../../lib/api';

export function DealPipelineWidget() {
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
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Unanswered */}
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700">Unanswered</span>
            <span className="bg-red-100 text-red-700 text-xs font-semibold px-2 py-1 rounded-full">
              {unanswered.length}
            </span>
          </div>
          {unanswered.map((deal) => (
            <div key={deal._id} className="bg-white p-3 rounded-lg border border-slate-200 mb-2 shadow-sm">
              <p className="text-sm font-medium">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <button
                onClick={() => router.push('/dashboard/deals')}
                className="w-full inline-flex justify-center items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs px-3 py-1.5 rounded transition-colors"
              >
                <PenTool className="w-3.5 h-3.5" /> Generate Draft
              </button>
            </div>
          ))}
          {unanswered.length === 0 && (
             <p className="text-xs text-slate-400 text-center py-2">No unanswered deals.</p>
          )}
        </div>

        {/* Drafts Pending Approval */}
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700">Pending Approval</span>
            <span className="bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-1 rounded-full">
              {pending.length}
            </span>
          </div>
          {pending.map((deal) => (
            <div key={deal._id} className="bg-white p-3 rounded-lg border border-amber-200 mb-2 shadow-sm border-l-2 border-l-amber-500">
              <p className="text-sm font-medium">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <button
                onClick={() => router.push('/dashboard/deals')}
                className="w-full inline-flex justify-center items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white text-xs px-3 py-1.5 rounded transition-colors"
              >
                <CheckCircle className="w-3.5 h-3.5" /> Review Draft
              </button>
            </div>
          ))}
          {pending.length === 0 && (
             <p className="text-xs text-slate-400 text-center py-2">No drafts to review.</p>
          )}
        </div>

        {/* In Negotiation */}
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-slate-700">In Negotiation</span>
            <span className="bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-1 rounded-full">
              {negotiating.length}
            </span>
          </div>
          {negotiating.map((deal) => (
            <div key={deal._id} className="bg-white p-3 rounded-lg border border-slate-200 mb-2 shadow-sm">
              <p className="text-sm font-medium">{deal.brand?.name || 'Unknown Brand'}</p>
              <p className="text-xs text-slate-500 mb-2">₹{deal.financials?.amount_inr?.toLocaleString('en-IN')}</p>
              <div className="inline-flex items-center gap-1.5 text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded">
                <Clock className="w-3.5 h-3.5" /> Awaiting Response
              </div>
            </div>
          ))}
          {negotiating.length === 0 && (
             <p className="text-xs text-slate-400 text-center py-2">No active negotiations.</p>
          )}
        </div>
      </div>
    </div>
  );
}
