'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, ShieldAlert, Check, X, Mail } from 'lucide-react';
import { API_BASE, getMe } from '../../../lib/api';
import type { Creator } from '../../../lib/types';

interface HitlItem {
  _id: string;
  agent: string;
  action_type: string;
  decision: {
    reasoning_summary: string;
    confidence: number;
    email_subject: string;
    sender_email: string;
    thread_id: string;
  };
}

export default function HitlQueuePage() {
  const router = useRouter();
  const [items, setItems] = useState<HitlItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creator, setCreator] = useState<Creator | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) setCreator(me);

        const res = await fetch(`${API_BASE}/hitl/queue`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setItems(data);
        }
      } catch {
        if (!cancelled) router.replace('/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  const handleResolve = async (actionId: string, resolution: 'extract' | 'discard') => {
    try {
      setItems((prev) => prev.filter(i => i._id !== actionId));
      await fetch(`${API_BASE}/hitl/resolve/${actionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolution }),
        credentials: 'include',
      });
    } catch (err) {
      console.error('Failed to resolve item:', err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-slate-50 px-6 py-8 md:px-10">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-amber-500" /> Human Review Queue
          </h1>
          <p className="text-slate-500 mt-2">
            ThreadComb flagged these emails as potential deals, but confidence was below the 85% threshold.
          </p>
        </header>

        {items.length === 0 ? (
          <div className="tc-card p-12 text-center flex flex-col items-center justify-center">
            <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mb-4">
              <Check className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-medium text-slate-900 mb-2">Queue is Empty</h2>
            <p className="text-slate-500">All pending reviews have been processed.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {items.map((item) => (
              <div key={item._id} className="tc-card p-6 border border-slate-200">
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                        Confidence: {(item.decision.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="text-xs text-slate-400">Thread ID: {item.decision.thread_id}</span>
                    </div>
                    
                    <h3 className="font-semibold text-lg text-slate-900 flex items-center gap-2 mb-1">
                      <Mail className="w-4 h-4 text-slate-400" />
                      {item.decision.email_subject || '(No Subject)'}
                    </h3>
                    <p className="text-sm text-slate-500 mb-4">From: {item.decision.sender_email}</p>
                    
                    <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                      <p className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-1">Reason for Review</p>
                      <p className="text-sm text-slate-700">{item.decision.reasoning_summary}</p>
                    </div>
                  </div>
                  
                  <div className="flex flex-col gap-2 min-w-[200px]">
                    <button
                      onClick={() => handleResolve(item._id, 'extract')}
                      className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      <Check className="w-4 h-4" /> Mark as Deal Signal
                    </button>
                    <button
                      onClick={() => handleResolve(item._id, 'discard')}
                      className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors"
                    >
                      <X className="w-4 h-4" /> Discard (Not a Deal)
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
