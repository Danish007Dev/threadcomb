'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  X,
  Send,
  Pencil,
  RotateCcw,
  Ban,
  Loader2,
  CheckCircle2,
  Sparkles,
  TrendingUp,
  Languages,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { BrandScoreBar } from './BrandScoreBar';
import { FlagsPanel } from './FlagsPanel';
import { getDealDraft, approveDeal, rejectDeal, generateDealDraft } from '../../../lib/api';
import type { DealDraft, InboundDeal } from '../../../lib/api';

interface ShadowDraftModalProps {
  deal: InboundDeal;
  onClose: () => void;
  onActionComplete: (dealId: string, action: string, message: string) => void;
}

export function ShadowDraftModal({ deal, onClose, onActionComplete }: ShadowDraftModalProps) {
  const [draft, setDraft] = useState<DealDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftText, setDraftText] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [isRevising, setIsRevising] = useState(false);

  const fetchDraft = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getDealDraft(deal._id);
      setDraft(d);
      setDraftText(d.draft_text);
    } catch (err: any) {
      setError(err.message || 'Failed to load draft');
    } finally {
      setLoading(false);
    }
  }, [deal._id]);

  useEffect(() => {
    fetchDraft();
  }, [fetchDraft]);

  // Close on Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const handleApprove = async () => {
    setIsSending(true);
    try {
      const isEdited = draftText !== draft?.draft_text;
      const result = await approveDeal(deal._id, draftText, isEdited ? 'edited' : 'approved');
      const brandName = deal.brand?.name || draft?.brand_name || 'Brand';
      onActionComplete(
        deal._id,
        'approved',
        `Reply sent to ${brandName}. Follow-up reminder set for ${new Date(result.follow_up_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}.`
      );
    } catch (err: any) {
      setError(err.message || 'Failed to send');
    } finally {
      setIsSending(false);
    }
  };

  const handleReject = async () => {
    setIsRejecting(true);
    try {
      await rejectDeal(deal._id);
      onActionComplete(deal._id, 'rejected', 'Deal marked as rejected. No email sent.');
    } catch (err: any) {
      setError(err.message || 'Failed to reject');
    } finally {
      setIsRejecting(false);
    }
  };

  const handleRevise = async () => {
    setIsRevising(true);
    try {
      await generateDealDraft(deal._id);
      // Wait a moment then refetch
      setTimeout(() => fetchDraft(), 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to request revision');
    } finally {
      setIsRevising(false);
    }
  };

  const charCount = draftText.length;
  const wordCount = draftText.trim().split(/\s+/).filter(Boolean).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="shadow-draft-modal"
    >
      <div className="relative w-full max-w-5xl mx-4 max-h-[90vh] bg-card rounded-2xl border border-border/40 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/40 bg-card/80 backdrop-blur-sm">
          <div>
            <h2 className="font-heading text-lg font-medium text-foreground">
              Draft Reply — {deal.brand?.name || draft?.brand_name || 'Brand Deal'}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review the context and draft before sending
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-accent transition-colors"
            data-testid="close-modal-btn"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <span className="ml-2 text-sm text-muted-foreground">Loading draft...</span>
            </div>
          ) : error && !draft ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : draft ? (
            <div className="grid grid-cols-1 lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-border/40">
              {/* Left panel — Context */}
              <div className="lg:col-span-2 p-5 md:p-6 space-y-5 overflow-y-auto max-h-[60vh] lg:max-h-none">
                {/* Brand + Score */}
                <div className="space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Brand Context
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground text-sm">
                      {draft.brand_name || 'Unknown'}
                    </span>
                    {draft.brand_is_new && (
                      <span className="text-[10px] font-medium text-amber-600 bg-amber-50 dark:bg-amber-950/30 px-1.5 py-0.5 rounded">
                        First Time
                      </span>
                    )}
                  </div>
                  <BrandScoreBar score={draft.brand_reliability_score} />
                </div>

                {/* Rate comparison */}
                {(draft.offered_amount || draft.market_p50) && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Rate Comparison
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="p-2.5 rounded-lg bg-accent/30 border border-border/20">
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Offered</p>
                        <p className="text-sm font-bold text-foreground mt-0.5">
                          {draft.offered_amount
                            ? `₹${draft.offered_amount.toLocaleString('en-IN')}`
                            : draft.offered_amount_ambiguous ? 'Unclear' : 'Not stated'}
                        </p>
                      </div>
                      <div className="p-2.5 rounded-lg bg-accent/30 border border-border/20">
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Market P50</p>
                        <p className="text-sm font-bold text-foreground mt-0.5">
                          {draft.market_p50
                            ? `₹${draft.market_p50.toLocaleString('en-IN')}`
                            : 'No data'}
                        </p>
                      </div>
                    </div>
                    {draft.rate_gap_percentage !== null && (
                      <div className={cn(
                        'text-xs font-medium px-2 py-1 rounded',
                        draft.rate_gap_percentage < -15
                          ? 'text-red-600 bg-red-50 dark:bg-red-950/20'
                          : draft.rate_gap_percentage > 0
                          ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/20'
                          : 'text-amber-600 bg-amber-50 dark:bg-amber-950/20'
                      )}>
                        <TrendingUp className="w-3 h-3 inline mr-1" />
                        {draft.rate_gap_percentage > 0 ? '+' : ''}{draft.rate_gap_percentage}% vs market
                      </div>
                    )}
                  </div>
                )}

                {/* Similar deals */}
                {draft.similar_deals_summary && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Similar Deals
                    </p>
                    <p className="text-xs text-muted-foreground bg-accent/30 p-2.5 rounded-lg border border-border/20">
                      <Sparkles className="w-3 h-3 inline mr-1 text-primary" />
                      {draft.similar_deals_summary}
                    </p>
                  </div>
                )}

                {/* Flags */}
                <FlagsPanel flags={draft.flags} />

                {/* Voice compliance (subtle) */}
                <div className="pt-2 border-t border-border/30">
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span className="uppercase tracking-wider font-semibold">Voice match</span>
                    <span className={cn(
                      'font-bold',
                      draft.voice_compliance_score >= 0.75 ? 'text-emerald-500' : 'text-amber-500'
                    )}>
                      {Math.round(draft.voice_compliance_score * 100)}%
                    </span>
                    <span className="text-muted-foreground/50">•</span>
                    <span className="capitalize">{draft.model_used.replace('gemini-', '')}</span>
                    {draft.generation_latency_ms && (
                      <>
                        <span className="text-muted-foreground/50">•</span>
                        <span>{(draft.generation_latency_ms / 1000).toFixed(1)}s</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Right panel — Draft */}
              <div className="lg:col-span-3 p-5 md:p-6 flex flex-col">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Draft Reply
                  </p>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <Languages className="w-3 h-3" />
                    <span>{draft.draft_language === 'hi-en' ? 'Hindi-English' : draft.draft_language === 'hi' ? 'Hindi' : 'English'}</span>
                    <span className="text-muted-foreground/50">•</span>
                    <span>{wordCount} words</span>
                    <span className="text-muted-foreground/50">•</span>
                    <span>{charCount} chars</span>
                  </div>
                </div>

                <textarea
                  value={draftText}
                  onChange={(e) => {
                    setDraftText(e.target.value);
                    if (!isEditing) setIsEditing(true);
                  }}
                  className="flex-1 min-h-[250px] w-full p-4 rounded-xl bg-accent/20 border border-border/40 text-sm text-foreground leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all font-mono"
                  data-testid="draft-textarea"
                />

                {error && (
                  <p className="text-xs text-destructive mt-2">{error}</p>
                )}

                {/* Action buttons */}
                <div className="flex items-center gap-2 mt-4 flex-wrap">
                  <button
                    onClick={handleApprove}
                    disabled={isSending || !draftText.trim()}
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm disabled:opacity-50"
                    data-testid="approve-send-btn"
                  >
                    {isSending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                    {isEditing ? 'Edit & Send' : 'Approve & Send'}
                  </button>

                  <button
                    onClick={handleRevise}
                    disabled={isRevising}
                    className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg bg-accent text-accent-foreground text-sm font-medium hover:bg-accent/80 transition-colors disabled:opacity-50"
                    data-testid="revise-btn"
                  >
                    {isRevising ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <RotateCcw className="w-4 h-4" />
                    )}
                    Revise
                  </button>

                  <button
                    onClick={handleReject}
                    disabled={isRejecting}
                    className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors disabled:opacity-50 ml-auto"
                    data-testid="reject-btn"
                  >
                    {isRejecting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Ban className="w-4 h-4" />
                    )}
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
