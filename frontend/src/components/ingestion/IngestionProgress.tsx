'use client';

import { useMemo } from 'react';
import { CheckCircle2, Loader2, Signal, SignalLow, AlertTriangle } from 'lucide-react';

import { useIngestionStatus } from '../../hooks/useIngestionStatus';
import { cn } from '../../lib/utils';

interface IngestionProgressProps {
  creatorId: string;
  jobId: string;
  className?: string;
}

export function IngestionProgress({ creatorId, jobId, className }: IngestionProgressProps) {
  const { latestEvent, statusSnapshot, isConnected } = useIngestionStatus(
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
  const totalThreads =
    latestEvent?.total ?? statusSnapshot?.total_threads_found ?? passedGate + failedGate;
  const processed = Math.min(passedGate + failedGate, totalThreads || 0);
  const progressPct = totalThreads ? Math.round((processed / totalThreads) * 100) : 0;

  const queued = statusSnapshot?.threads_queued_for_extraction ?? passedGate;
  const hitlQueue = latestEvent?.hitl_queue ?? 0;

  const statusIcon = useMemo(() => {
    if (status === 'ingestion_error') return <AlertTriangle className="w-4 h-4 text-destructive" />;
    if (status === 'gate_complete' || status === 'queued_for_extraction') {
      return <CheckCircle2 className="w-4 h-4 text-primary" />;
    }
    if (status === 'connected') return <Signal className="w-4 h-4 text-primary" />;
    return <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />;
  }, [status]);

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
            <span className="capitalize">{status.replace(/_/g, ' ')}</span>
          </div>
        </div>
      </header>

      <div className="space-y-2">
        <div className="h-2 rounded-full bg-muted">
          <div
            className="h-2 rounded-full bg-primary transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{processed} processed</span>
          <span>{totalThreads} total</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
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
      </div>
    </section>
  );
}
