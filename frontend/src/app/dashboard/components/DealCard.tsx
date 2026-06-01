'use client';

import { useState } from 'react';
import {
  Handshake,
  AlertTriangle,
  Sparkles,
  Loader2,
  Eye,
  Wand2,
  Clock,
  Building2,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { BrandScoreBar } from './BrandScoreBar';
import type { InboundDeal } from '../../../lib/api';

const DEAL_TYPE_LABELS: Record<string, string> = {
  instagram_reel: 'Instagram Reel',
  instagram_post: 'Instagram Post',
  instagram_story: 'Instagram Story',
  youtube_dedicated: 'YouTube Dedicated',
  youtube_integration: 'YouTube Integration',
  youtube_shorts: 'YouTube Shorts',
  multi_platform: 'Multi-Platform',
  other: 'Other',
};

interface DealCardProps {
  deal: InboundDeal;
  onViewDraft: (dealId: string) => void;
  onGenerateDraft: (dealId: string) => void;
  isGenerating?: boolean;
}

export function DealCard({ deal, onViewDraft, onGenerateDraft, isGenerating }: DealCardProps) {
  const brandName = deal.brand?.name || deal.raw_signals?.brand_contact_email?.split('@')[1] || 'Unknown Brand';
  const brandDomain = deal.brand?.domain || deal.raw_signals?.brand_contact_email?.split('@')[1] || '';
  const dealType = deal.deal_type ? DEAL_TYPE_LABELS[deal.deal_type] || deal.deal_type : 'Brand Deal';
  const deliverables = deal.raw_signals?.deliverables || [];
  const amountInr = deal.financials?.amount_inr;
  const amountAmbiguous = deal.financials?.amount_ambiguity_flag;
  const reliability = deal.brand?.payment_reliability ?? 0.5;
  const isNewBrand = !deal.brand;
  const createdAt = deal.created_at ? new Date(deal.created_at) : null;

  return (
    <div
      className={cn(
        'tc-card p-5 md:p-6 transition-all hover:shadow-md hover:border-primary/20',
        deal.has_pending_draft && 'border-l-4 border-l-primary',
      )}
      data-testid={`deal-card-${deal._id}`}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: Deal info */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* Brand & type */}
          <div className="flex items-center gap-2 flex-wrap">
            <Building2 className="w-4 h-4 text-primary shrink-0" />
            <h3 className="font-medium text-foreground text-sm truncate">{brandName}</h3>
            {brandDomain && (
              <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {brandDomain}
              </span>
            )}
            {isNewBrand && (
              <span className="text-[10px] font-medium text-amber-600 bg-amber-50 dark:bg-amber-950/30 px-1.5 py-0.5 rounded">
                New Brand
              </span>
            )}
          </div>

          {/* Deal details row */}
          <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1 bg-accent/50 px-2 py-0.5 rounded-md font-medium text-accent-foreground">
              <Handshake className="w-3 h-3" />
              {dealType}
            </span>

            {amountInr && !amountAmbiguous ? (
              <span className="font-semibold text-foreground">
                ₹{amountInr.toLocaleString('en-IN')}
              </span>
            ) : (
              <span className="italic text-muted-foreground/70">
                {amountAmbiguous ? 'Amount unclear' : 'Amount not stated'}
              </span>
            )}

            {deliverables.length > 0 && (
              <span className="truncate max-w-[200px]">
                {deliverables.slice(0, 2).join(', ')}
                {deliverables.length > 2 && ` +${deliverables.length - 2}`}
              </span>
            )}
          </div>

          {/* Brand score + date */}
          <div className="flex items-center gap-4">
            {deal.brand && (
              <BrandScoreBar score={reliability} compact showLabel={false} />
            )}
            {createdAt && (
              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {createdAt.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
              </span>
            )}
          </div>
        </div>

        {/* Right: Action button */}
        <div className="shrink-0">
          {deal.has_pending_draft ? (
            <button
              onClick={() => onViewDraft(deal._id)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity shadow-sm"
              data-testid={`view-draft-btn-${deal._id}`}
            >
              <Eye className="w-3.5 h-3.5" />
              View Draft
            </button>
          ) : (
            <button
              onClick={() => onGenerateDraft(deal._id)}
              disabled={isGenerating}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-accent text-accent-foreground text-xs font-medium hover:bg-accent/80 transition-colors disabled:opacity-50"
              data-testid={`generate-draft-btn-${deal._id}`}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Wand2 className="w-3.5 h-3.5" />
                  Generate Draft
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
