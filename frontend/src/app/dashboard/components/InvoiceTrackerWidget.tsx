'use client';

import { useEffect, useState } from 'react';
import { ReceiptText, Loader2, AlertCircle, FileWarning } from 'lucide-react';
import { API_BASE } from '../../../lib/api';
import { cn } from '../../../lib/utils';

interface InvoiceDraft {
  invoice_id: string;
  brand_name: string;
  amount_inr: number;
  days_overdue: int;
  urgency_score: number;
  recommended_tone: 'gentle' | 'firm' | 'final_notice';
  draft_text: string;
}

interface BatchFollowup {
  _id: string;
  total_overdue: number;
  drafts: InvoiceDraft[];
}

export function InvoiceTrackerWidget() {
  const [batch, setBatch] = useState<BatchFollowup | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/guardian/pending`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setBatch(data);
        }
      } catch {
        // ignore
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

  if (!batch || batch.drafts?.length === 0) {
    return (
      <div className="tc-card p-6 flex items-center justify-between border-emerald-200 bg-emerald-50">
        <div className="flex items-center gap-3">
          <ReceiptText className="w-5 h-5 text-emerald-600" />
          <h3 className="font-medium text-emerald-900">Invoice Tracker</h3>
        </div>
        <p className="text-sm text-emerald-700">All payments are on track.</p>
      </div>
    );
  }

  // Sort by urgency score descending
  const drafts = [...batch.drafts].sort((a, b) => b.urgency_score - a.urgency_score);

  return (
    <div className="tc-card p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <FileWarning className="w-5 h-5 text-rose-500" />
          <h3 className="font-medium text-lg text-foreground">Invoice Tracker</h3>
          <span className="bg-rose-100 text-rose-700 text-xs font-semibold px-2 py-0.5 rounded-full">
            {batch.total_overdue} Overdue
          </span>
        </div>
        <button className="bg-rose-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-rose-700 transition-colors">
          Review Follow-ups
        </button>
      </div>

      <div className="space-y-3">
        {drafts.map((draft) => {
          let toneColor = "bg-blue-100 text-blue-700";
          if (draft.recommended_tone === "firm") toneColor = "bg-amber-100 text-amber-700";
          if (draft.recommended_tone === "final_notice") toneColor = "bg-rose-100 text-rose-700";

          return (
            <div key={draft.invoice_id} className="flex items-center justify-between p-4 bg-white border border-slate-200 rounded-xl hover:border-slate-300 transition-colors shadow-sm">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-medium">
                  {draft.brand_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="font-medium text-slate-900">{draft.brand_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-sm text-slate-500">₹{draft.amount_inr?.toLocaleString('en-IN')}</span>
                    <span className="text-slate-300">•</span>
                    <span className="text-sm text-rose-600 font-medium">{draft.days_overdue} days overdue</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right hidden sm:block">
                  <p className="text-xs text-slate-400 mb-1">Urgency Score</p>
                  <p className="text-sm font-semibold text-slate-700">{draft.urgency_score}</p>
                </div>
                <div className={cn("px-3 py-1.5 rounded-md text-xs font-medium uppercase tracking-wider", toneColor)}>
                  {draft.recommended_tone.replace('_', ' ')}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
