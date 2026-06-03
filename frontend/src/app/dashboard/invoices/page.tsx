'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ReceiptText,
  ArrowLeft,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Send,
  SkipForward,
  IndianRupee,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { ThreadCombLogo } from '../../../components/brand/Logo';
import { cn } from '../../../lib/utils';
import {
  getMe,
  getGuardianPending,
  triggerGuardianRun,
  approveSingleFollowup,
} from '../../../lib/api';
import type { Creator } from '../../../lib/types';
import type { PendingFollowups, InvoiceFollowupDraft } from '../../../lib/api';

type TabKey = 'pending' | 'sent' | 'skipped';

export default function InvoicesPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);
  const [followups, setFollowups] = useState<PendingFollowups | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('pending');
  const [runningGuardian, setRunningGuardian] = useState(false);
  const [sendingIds, setSendingIds] = useState<Set<string>>(new Set());
  const [sentIds, setSentIds] = useState<Set<string>>(new Set());
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) setCreator(me);

        const pending = await getGuardianPending();
        if (!cancelled) setFollowups(pending);
      } catch {
        if (!cancelled) router.replace('/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  const handleRunGuardian = async () => {
    setRunningGuardian(true);
    try {
      await triggerGuardianRun();
      // Wait a moment then refresh data
      await new Promise((r) => setTimeout(r, 3000));
      const updated = await getGuardianPending();
      setFollowups(updated);
    } catch (err) {
      console.error('Guardian run failed:', err);
    } finally {
      setRunningGuardian(false);
    }
  };

  const handleApprove = async (draft: InvoiceFollowupDraft) => {
    setSendingIds((prev) => new Set(prev).add(draft.invoice_id));
    try {
      await approveSingleFollowup(draft.invoice_id, draft.draft_text);
      setSentIds((prev) => new Set(prev).add(draft.invoice_id));
    } catch (err) {
      console.error('Approve failed:', err);
    } finally {
      setSendingIds((prev) => {
        const next = new Set(prev);
        next.delete(draft.invoice_id);
        return next;
      });
    }
  };

  const handleSkip = (invoiceId: string) => {
    setSkippedIds((prev) => new Set(prev).add(invoiceId));
  };

  const drafts = followups?.drafts || [];
  const pendingDrafts = drafts.filter(
    (d) => !sentIds.has(d.invoice_id) && !skippedIds.has(d.invoice_id) && d.creator_action !== 'approved' && d.creator_action !== 'skipped'
  );
  const sentDrafts = drafts.filter(
    (d) => sentIds.has(d.invoice_id) || d.creator_action === 'approved'
  );
  const skippedDrafts = drafts.filter(
    (d) => skippedIds.has(d.invoice_id) || d.creator_action === 'skipped'
  );

  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: 'pending', label: 'Pending Review', count: pendingDrafts.length },
    { key: 'sent', label: 'Sent', count: sentDrafts.length },
    { key: 'skipped', label: 'Skipped', count: skippedDrafts.length },
  ];

  const activeDrafts =
    activeTab === 'pending' ? pendingDrafts : activeTab === 'sent' ? sentDrafts : skippedDrafts;

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background" data-testid="invoices-page">
      {/* Header */}
      <header className="border-b border-border/40 bg-card/60 backdrop-blur-sm px-6 md:px-10 py-5">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-muted-foreground hover:text-foreground transition-colors"
              data-testid="back-to-dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <ThreadCombLogo className="text-primary" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRunGuardian}
              disabled={runningGuardian}
              data-testid="run-guardian-btn"
            >
              {runningGuardian ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
                  Checking...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 mr-2" />
                  Run Invoice Check
                </>
              )}
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-10 py-8 space-y-6">
        {/* Page title */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
              <ReceiptText className="w-5 h-5" />
            </div>
            <h1 className="font-heading text-2xl md:text-3xl tracking-tight font-medium text-foreground">
              Invoice Follow-ups
            </h1>
          </div>
          <p className="text-sm text-muted-foreground ml-[52px]">
            Revenue Guardian drafts follow-up emails for overdue invoices. Review, approve, or skip each one.
          </p>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="tc-card px-4 py-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Total Overdue</p>
            <p className="text-xl font-semibold text-foreground mt-1">{followups?.total_overdue ?? 0}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Pending</p>
            <p className="text-xl font-semibold text-amber-600 dark:text-amber-400 mt-1">{pendingDrafts.length}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Sent</p>
            <p className="text-xl font-semibold text-emerald-600 dark:text-emerald-400 mt-1">{sentDrafts.length}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Skipped</p>
            <p className="text-xl font-semibold text-muted-foreground mt-1">{skippedDrafts.length}</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-muted/50 rounded-lg w-fit">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'px-4 py-2 text-sm font-medium rounded-md transition-all',
                activeTab === tab.key
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
              {tab.count > 0 && (
                <span className="ml-2 text-xs px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Draft cards */}
        {activeDrafts.length === 0 ? (
          <div className="tc-card p-10 text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-muted mb-4">
              {activeTab === 'pending' ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-500" />
              ) : (
                <Clock className="w-5 h-5 text-muted-foreground" />
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              {activeTab === 'pending'
                ? 'No pending follow-ups. Run an invoice check to scan for overdue payments.'
                : `No ${activeTab} follow-ups yet.`}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {activeDrafts.map((draft) => (
              <div
                key={draft.invoice_id}
                className="tc-card p-5 space-y-4"
                data-testid={`invoice-draft-${draft.invoice_id}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'w-2 h-2 rounded-full shrink-0',
                        draft.days_overdue > 30
                          ? 'bg-red-500'
                          : draft.days_overdue > 14
                          ? 'bg-amber-500'
                          : 'bg-yellow-400'
                      )}
                    />
                    <div>
                      <p className="text-sm font-medium text-foreground">{draft.brand_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {draft.days_overdue} days overdue • Tone: {draft.tone}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-foreground flex items-center gap-1">
                      <IndianRupee className="w-3.5 h-3.5" />
                      {draft.amount_inr?.toLocaleString('en-IN') ?? '—'}
                    </p>
                  </div>
                </div>

                {/* Draft preview */}
                <div className="bg-muted/30 rounded-lg p-3 text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap max-h-32 overflow-y-auto">
                  {draft.draft_text}
                </div>

                {/* Actions */}
                {activeTab === 'pending' && (
                  <div className="flex gap-2 justify-end">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleSkip(draft.invoice_id)}
                      className="text-muted-foreground"
                    >
                      <SkipForward className="w-3.5 h-3.5 mr-1.5" />
                      Skip
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleApprove(draft)}
                      disabled={sendingIds.has(draft.invoice_id)}
                    >
                      {sendingIds.has(draft.invoice_id) ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <Send className="w-3.5 h-3.5 mr-1.5" />
                          Send Follow-up
                        </>
                      )}
                    </Button>
                  </div>
                )}
                {activeTab === 'sent' && (
                  <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Sent{draft.sent_at ? ` on ${new Date(draft.sent_at).toLocaleDateString()}` : ''}</span>
                  </div>
                )}
                {activeTab === 'skipped' && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <XCircle className="w-3.5 h-3.5" />
                    <span>Skipped by you</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
