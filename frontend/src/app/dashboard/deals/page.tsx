'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Handshake,
  ArrowLeft,
  Loader2,
  Inbox,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { getMe, getInboundDeals, generateDealDraft } from '../../../lib/api';
import type { Creator } from '../../../lib/types';
import type { InboundDeal } from '../../../lib/api';
import { DealCard } from '../components/DealCard';
import { ShadowDraftModal } from '../components/ShadowDraftModal';
import { ThreadCombLogo } from '../../../components/brand/Logo';
import { useIngestionStatus } from '../../../hooks/useIngestionStatus';

export default function DealsPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [deals, setDeals] = useState<InboundDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [generatingDealId, setGeneratingDealId] = useState<string | null>(null);
  const [selectedDeal, setSelectedDeal] = useState<InboundDeal | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const { events } = useIngestionStatus(creator?.creator_id);

  const fetchDeals = useCallback(async () => {
    try {
      const data = await getInboundDeals();
      setDeals(data);
    } catch (err) {
      console.error('Failed to fetch deals:', err);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) {
          setCreator(me);
          await fetchDeals();
        }
      } catch {
        if (!cancelled) router.replace('/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router, fetchDeals]);

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
    } else if (latest.event === 'extraction_complete') {
      setToast({ message: latest.message || 'Brand details extracted. Generating reply draft...', type: 'info' });
      fetchDeals();
    } else if (latest.event === 'draft_ready') {
      setToast({ message: latest.message || 'New reply draft is ready.', type: 'success' });
      fetchDeals();
      setGeneratingDealId(null);
    }
  }, [events, fetchDeals]);

  const handleGenerateDraft = async (dealId: string) => {
    setGeneratingDealId(dealId);
    try {
      await generateDealDraft(dealId);
      setToast({ message: 'Draft is being generated — it will appear in a few seconds.', type: 'success' });
      // Poll for draft readiness
      setTimeout(async () => {
        await fetchDeals();
        setGeneratingDealId(null);
      }, 8000);
    } catch (err: any) {
      setToast({ message: err.message || 'Failed to generate draft', type: 'error' });
      setGeneratingDealId(null);
    }
  };

  const handleViewDraft = (dealId: string) => {
    const deal = deals.find(d => d._id === dealId);
    if (deal) setSelectedDeal(deal);
  };

  const handleModalActionComplete = async (dealId: string, action: string, message: string) => {
    setSelectedDeal(null);
    setToast({ message, type: 'success' });
    await fetchDeals();
  };

  // Sort: pending drafts first, then unanswered, then by date
  const sortedDeals = [...deals].sort((a, b) => {
    if (a.has_pending_draft && !b.has_pending_draft) return -1;
    if (!a.has_pending_draft && b.has_pending_draft) return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const pendingCount = deals.filter(d => d.has_pending_draft).length;

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background">
      {/* Header */}
      <header className="border-b border-border/40 bg-background/80 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/dashboard')}
              className="p-2 rounded-lg hover:bg-accent transition-colors"
              data-testid="back-to-dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <h1 className="font-heading text-lg font-medium text-foreground flex items-center gap-2">
                <Handshake className="w-5 h-5 text-primary" />
                Deal Inbox
              </h1>
              <p className="text-xs text-muted-foreground">
                {deals.length} deal{deals.length !== 1 ? 's' : ''}
                {pendingCount > 0 && (
                  <span className="text-primary font-semibold ml-1">
                    · {pendingCount} draft{pendingCount > 1 ? 's' : ''} waiting
                  </span>
                )}
              </p>
            </div>
          </div>
          <ThreadCombLogo className="text-primary hidden sm:block" />
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-6 py-8 tc-grain">
        {deals.length === 0 ? (
          <div className="flex flex-col items-center justify-center min-h-[50vh] text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-accent text-accent-foreground mb-4">
              <Inbox className="w-6 h-6" />
            </div>
            <h2 className="font-heading text-2xl font-medium text-foreground">No deals yet</h2>
            <p className="text-sm text-muted-foreground mt-2 max-w-md">
              When brand deal emails arrive in your inbox, they'll appear here with AI-generated reply drafts.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {sortedDeals.map(deal => (
              <DealCard
                key={deal._id}
                deal={deal}
                onViewDraft={handleViewDraft}
                onGenerateDraft={handleGenerateDraft}
                isGenerating={generatingDealId === deal._id}
              />
            ))}
          </div>
        )}
      </main>

      {/* Shadow Draft Modal */}
      {selectedDeal && (
        <ShadowDraftModal
          deal={selectedDeal}
          onClose={() => setSelectedDeal(null)}
          onActionComplete={handleModalActionComplete}
        />
      )}

      {/* Toast */}
      {toast && (
        <div
          className={cn(
            'fixed bottom-6 right-6 z-50 max-w-sm px-4 py-3 rounded-xl shadow-lg border text-sm font-medium animate-in slide-in-from-bottom-4 fade-in duration-300',
            toast.type === 'success'
              ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400'
              : toast.type === 'error'
              ? 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400'
              : 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-400'
          )}
          data-testid="deals-toast"
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
