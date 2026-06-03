'use client';

import { useMemo } from 'react';
import {
  CheckCircle2,
  Loader2,
  Signal,
  SignalLow,
  AlertTriangle,
  RefreshCw,
  Zap,
} from 'lucide-react';

import { useIngestionStatus } from '../../hooks/useIngestionStatus';
import { cn } from '../../lib/utils';
import { Button } from '../ui/button';

interface IngestionProgressProps {
  creatorId: string;
  jobId: string;
  className?: string;
  onRetry?: () => void;
}

export function IngestionProgress({ creatorId, jobId, className, onRetry }: IngestionProgressProps) {
  const { events, latestEvent, statusSnapshot, isConnected } = useIngestionStatus(
    creatorId,
    jobId
  );

  const status = statusSnapshot?.status || latestEvent?.event || 'pending';
  const message =
    latestEvent?.message ||
    (statusSnapshot ? `Current state: ${statusSnapshot.status}` : 'Waiting for ingestion updates...');

  const passedGate =
    latestEvent?.passed_gate ?? latestEvent?.passed ?? statusSnapshot?.threads_passed_gate ?? 0;
  const failedGate = latestEvent?.failed_gate ?? latestEvent?.failed ?? 0;
  const rateLimited = (latestEvent as any)?.rate_limited ?? 0;
  const totalThreads =
    latestEvent?.total ?? statusSnapshot?.total_threads_found ?? passedGate + failedGate;
  const processed = Math.min(passedGate + failedGate + rateLimited, totalThreads || 0);
  const progressPct = totalThreads ? Math.round((processed / totalThreads) * 100) : 0;

  const queued = statusSnapshot?.threads_queued_for_extraction ?? passedGate;
  const hitlQueue = latestEvent?.hitl_queue ?? 0;

  // Detect failure/rate-limit events
  const failureEvent = useMemo(() => {
    return events.find(
      (e) => e.event === 'ingestion_failed' || e.event === 'ingestion_rate_limited'
    );
  }, [events]);

  const isFailure = !!failureEvent;
  const failureReason = (failureEvent as any)?.reason || 'unknown';
  const canRetry = (failureEvent as any)?.can_retry ?? true;

  const statusIcon = useMemo(() => {
    if (isFailure) return <AlertTriangle className="w-4 h-4 text-destructive" />;
    if (status === 'ingestion_error') return <AlertTriangle className="w-4 h-4 text-destructive" />;
    if (status === 'gate_complete' || status === 'queued_for_extraction') {
      return <CheckCircle2 className="w-4 h-4 text-primary" />;
    }
    if (status === 'connected') return <Signal className="w-4 h-4 text-primary" />;
    return <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />;
  }, [status, isFailure]);

  return (
    <section className={cn('tc-card p-6 md:p-7 space-y-4', className)}>
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Ingestion</p>
          <h3 className="font-heading text-xl text-foreground mt-2">Thread scan progress</h3>
          <p className="text-sm text-muted-foreground mt-2">{message}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {isConnected ? (
              <Signal className="w-4 h-4 text-primary" />
            ) : (
              <SignalLow className="w-4 h-4 text-muted-foreground" />
            )}
            <span>{isConnected ? 'Live' : 'Reconnecting'}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {statusIcon}
            <span className="capitalize">{isFailure ? 'Failed' : status.replace(/_/g, ' ')}</span>
          </div>
        </div>
      </header>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="h-2 rounded-full bg-muted">
          <div
            className={cn(
              'h-2 rounded-full transition-all',
              isFailure ? 'bg-destructive' : 'bg-primary'
            )}
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{processed} processed</span>
          <span>{totalThreads} total</span>
        </div>
      </div>

      {/* Error banner */}
      {isFailure && (
        <div
          className={cn(
            'rounded-xl border p-4 space-y-3',
            failureReason === 'rate_limited'
              ? 'bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-900'
              : 'bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900'
          )}
        >
          <div className="flex items-start gap-3">
            {failureReason === 'rate_limited' ? (
              <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            )}
            <div>
              <p
                className={cn(
                  'text-sm font-medium',
                  failureReason === 'rate_limited'
                    ? 'text-amber-800 dark:text-amber-300'
                    : 'text-red-800 dark:text-red-300'
                )}
              >
                {failureReason === 'rate_limited'
                  ? 'AI Service Rate Limit Reached'
                  : failureReason === 'no_deals_found'
                  ? 'No Brand Deals Found'
                  : 'Audit Failed'}
              </p>
              <p
                className={cn(
                  'text-xs mt-1',
                  failureReason === 'rate_limited'
                    ? 'text-amber-700 dark:text-amber-400'
                    : 'text-red-700 dark:text-red-400'
                )}
              >
                {failureEvent?.message}
              </p>
            </div>
          </div>
          {canRetry && onRetry && (
            <Button
              size="sm"
              variant="outline"
              onClick={onRetry}
              className={cn(
                'w-full',
                failureReason === 'rate_limited'
                  ? 'border-amber-300 text-amber-800 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-300'
                  : 'border-red-300 text-red-800 hover:bg-red-100 dark:border-red-800 dark:text-red-300'
              )}
            >
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              {failureReason === 'rate_limited' ? 'Retry (wait a minute first)' : 'Retry Audit'}
            </Button>
          )}
        </div>
      )}

      {/* Stats grid */}
      <div className={cn('grid gap-3 text-xs', rateLimited > 0 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-1 sm:grid-cols-3')}>
        <div className="rounded-lg border border-border/40 px-3 py-2">
          <p className="text-muted-foreground">Passed gate</p>
          <p className="text-sm font-semibold text-foreground">{passedGate}</p>
        </div>
        <div className="rounded-lg border border-border/40 px-3 py-2">
          <p className="text-muted-foreground">Queued</p>
          <p className="text-sm font-semibold text-foreground">{queued}</p>
        </div>
        <div className="rounded-lg border border-border/40 px-3 py-2">
          <p className="text-muted-foreground">HITL queue</p>
          <p className="text-sm font-semibold text-foreground">{hitlQueue}</p>
        </div>
        {rateLimited > 0 && (
          <div className="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/10 px-3 py-2">
            <p className="text-amber-700 dark:text-amber-400">Rate limited</p>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">{rateLimited}</p>
          </div>
        )}
      </div>
    </section>
  );
}
