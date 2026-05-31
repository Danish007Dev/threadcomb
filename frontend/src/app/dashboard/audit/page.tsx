'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Download,
  FileText,
  Shield,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { getMe, getAuditReport } from '../../../lib/api';
import type { Creator } from '../../../lib/types';
import type { AuditReport, AuditFinding } from '../../../lib/api';
import { cn } from '../../../lib/utils';

const SEVERITY_CONFIG: Record<string, { color: string; bgColor: string; Icon: typeof AlertTriangle }> = {
  high: { color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-900', Icon: AlertTriangle },
  medium: { color: 'text-amber-600 dark:text-amber-400', bgColor: 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900', Icon: AlertTriangle },
  low: { color: 'text-blue-600 dark:text-blue-400', bgColor: 'bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900', Icon: TrendingUp },
  positive: { color: 'text-emerald-600 dark:text-emerald-400', bgColor: 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900', Icon: CheckCircle2 },
};

export default function AuditPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (cancelled) return;
        setCreator(me);
        const auditReport = await getAuditReport(me.creator_id);
        if (cancelled) return;
        setReport(auditReport);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.message.includes('401')) {
          router.replace('/login');
          return;
        }
        setError('No audit report available yet. Start your audit from the dashboard.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-dvh flex items-center justify-center px-6">
        <div className="tc-card max-w-md w-full p-8 text-center">
          <FileText className="w-10 h-10 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-medium text-foreground mb-2">No Audit Report Yet</h2>
          <p className="text-sm text-muted-foreground mb-6">{error}</p>
          <Button onClick={() => router.push('/dashboard')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background">
      {/* Header */}
      <header className="border-b border-border/40 bg-background/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 md:px-10 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="p-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Skills Audit</p>
              <h1 className="font-heading text-lg text-foreground">{creator?.name || 'Creator'}</h1>
            </div>
          </div>
          {report.pdf_url && !report.pdf_url.startsWith('local://') && !report.pdf_url.startsWith('gcs_error://') && (
            <a
              href={report.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Download className="w-4 h-4" />
              PDF
            </a>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-10 py-8 space-y-6">
        {/* Executive Summary */}
        <div className="tc-card p-6 md:p-8">
          <h2 className="font-heading text-2xl text-foreground mb-3">Summary</h2>
          <p className="text-sm md:text-base text-muted-foreground leading-relaxed">
            {report.executive_summary}
          </p>
          {report.total_recoverable_value != null && report.total_recoverable_value > 0 && (
            <div className="mt-4 p-4 rounded-lg bg-primary/5 border border-primary/20">
              <p className="text-xs uppercase tracking-wider text-primary font-semibold">Identified Recoverable Value</p>
              <p className="text-3xl font-bold text-foreground mt-1">
                ₹{report.total_recoverable_value.toLocaleString('en-IN')}
              </p>
            </div>
          )}
          {report.total_recoverable_unknown && !report.total_recoverable_value && (
            <div className="mt-4 p-4 rounded-lg bg-muted border border-border/40">
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Recoverable Value</p>
              <p className="text-sm text-muted-foreground mt-1">
                Unknown — deal amounts not stated in emails. Deal count tracked below.
              </p>
            </div>
          )}
        </div>

        {/* Findings */}
        <div>
          <h2 className="font-heading text-xl text-foreground mb-4">Findings</h2>
          <div className="space-y-4">
            {report.findings.map((finding, idx) => {
              const config = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.low;
              const FindingIcon = config.Icon;
              return (
                <div
                  key={idx}
                  className={cn('tc-card p-5 md:p-6 border', config.bgColor)}
                >
                  <div className="flex items-start gap-3">
                    <FindingIcon className={cn('w-5 h-5 mt-0.5 shrink-0', config.color)} />
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-medium text-foreground">{finding.title}</h3>
                        <span className={cn('text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full', config.color, 'bg-white/60 dark:bg-black/20')}>
                          {finding.severity}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{finding.finding_text}</p>
                      {finding.value_inr != null && finding.value_inr > 0 && (
                        <p className="text-sm font-semibold text-foreground">
                          Value: ₹{finding.value_inr.toLocaleString('en-IN')}
                        </p>
                      )}
                      {finding.value_unknown && (
                        <p className="text-sm text-muted-foreground italic">
                          Value: Amount not stated in emails
                        </p>
                      )}
                      <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t border-border/30">
                        <p><span className="font-medium">Evidence:</span> {finding.evidence}</p>
                        <p><span className="font-medium">Recommendation:</span> {finding.recommendation}</p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Skills Map Summary */}
        {report.skills_map_summary && (
          <div className="tc-card p-6 md:p-8">
            <div className="flex items-center gap-3 mb-3">
              <Shield className="w-5 h-5 text-primary" />
              <h2 className="font-heading text-xl text-foreground">Here&apos;s what we learned about how you work</h2>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {report.skills_map_summary}
            </p>
          </div>
        )}

        {/* Data Quality Note */}
        {report.data_quality_note && (
          <div className="tc-card p-5 border border-border/40">
            <div className="flex items-center gap-3 mb-2">
              <FileText className="w-4 h-4 text-muted-foreground" />
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
                Note on Data Quality
              </p>
            </div>
            <p className="text-sm text-muted-foreground">
              {report.data_quality_note}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
