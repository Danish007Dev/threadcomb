'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  BarChart3,
  ArrowLeft,
  FileText,
  TrendingUp,
  ArrowUpRight,
  Loader2,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Briefcase,
  IndianRupee,
  Users,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { ThreadCombLogo } from '../../../components/brand/Logo';
import { cn } from '../../../lib/utils';
import { getMe, getAuditReport } from '../../../lib/api';
import type { Creator } from '../../../lib/types';
import type { AuditReport } from '../../../lib/api';

interface DashboardStats {
  totalDeals: number;
  totalInvoices: number;
  overdueCount: number;
  totalBrands: number;
}

export default function ReportsPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (cancelled) return;
        setCreator(me);

        // Fetch audit report
        try {
          const auditReport = await getAuditReport(me.creator_id);
          if (!cancelled) setReport(auditReport);
        } catch {
          // No report yet — that's fine
        }

        // Fetch aggregate stats from API
        try {
          const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
          const [dealsRes, invoicesRes] = await Promise.allSettled([
            fetch(`${API_BASE}/deals/inbound`, { credentials: 'include' }),
            fetch(`${API_BASE}/guardian/pending`, { credentials: 'include' }),
          ]);

          const deals = dealsRes.status === 'fulfilled' && dealsRes.value.ok
            ? await dealsRes.value.json()
            : [];
          const guardian = invoicesRes.status === 'fulfilled' && invoicesRes.value.ok
            ? await invoicesRes.value.json()
            : { total_overdue: 0 };

          if (!cancelled) {
            setStats({
              totalDeals: Array.isArray(deals) ? deals.length : 0,
              totalInvoices: 0,
              overdueCount: guardian.total_overdue || 0,
              totalBrands: Array.isArray(deals) ? new Set(deals.map((d: any) => d.brand_id)).size : 0,
            });
          }
        } catch {
          // Stats failed — non-critical
        }
      } catch {
        if (!cancelled) router.replace('/login');
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

  const findings = report?.findings || [];
  const highSeverity = findings.filter(f => f.severity === 'high');
  const mediumSeverity = findings.filter(f => f.severity === 'medium');
  const positiveSeverity = findings.filter(f => f.severity === 'positive');

  return (
    <div className="min-h-dvh bg-background" data-testid="reports-page">
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
            <ThreadCombLogo className="text-primary" />
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 md:px-10 py-8 space-y-8">
        {/* Page title */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
              <BarChart3 className="w-5 h-5" />
            </div>
            <h1 className="font-heading text-2xl md:text-3xl tracking-tight font-medium text-foreground">
              Reports
            </h1>
          </div>
          <p className="text-sm text-muted-foreground ml-[52px]">
            Overview of your audit results, deal activity, and revenue health.
          </p>
        </div>

        {/* Overview Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="tc-card px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <Briefcase className="w-3.5 h-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Total Deals</p>
            </div>
            <p className="text-xl font-semibold text-foreground">{stats?.totalDeals ?? '—'}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <Users className="w-3.5 h-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Brands</p>
            </div>
            <p className="text-xl font-semibold text-foreground">{stats?.totalBrands ?? '—'}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Overdue</p>
            </div>
            <p className="text-xl font-semibold text-amber-600 dark:text-amber-400">{stats?.overdueCount ?? '—'}</p>
          </div>
          <div className="tc-card px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <FileText className="w-3.5 h-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Findings</p>
            </div>
            <p className="text-xl font-semibold text-foreground">{findings.length || '—'}</p>
          </div>
        </div>

        {/* Audit Report Section */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-foreground uppercase tracking-wider">Skills Audit Report</h2>
            {report && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => router.push('/dashboard/audit')}
              >
                View Full Report
                <ArrowUpRight className="w-3.5 h-3.5 ml-1.5" />
              </Button>
            )}
          </div>

          {report ? (
            <div className="space-y-4">
              {/* Executive Summary */}
              <div className="tc-card p-5 md:p-6">
                <h3 className="text-sm font-medium text-foreground mb-2">Executive Summary</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {report.executive_summary}
                </p>
                {report.total_recoverable_value != null && report.total_recoverable_value > 0 && (
                  <div className="mt-4 p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <p className="text-xs uppercase tracking-wider text-primary font-semibold">Identified Recoverable Value</p>
                    <p className="text-3xl font-bold text-foreground mt-1">
                      <IndianRupee className="w-6 h-6 inline -mt-1" />
                      {report.total_recoverable_value.toLocaleString('en-IN')}
                    </p>
                  </div>
                )}
              </div>

              {/* Finding counts by severity */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="tc-card p-4 border border-red-200 dark:border-red-900 bg-red-50/50 dark:bg-red-950/10">
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                    <p className="text-xs text-red-600 dark:text-red-400 uppercase tracking-wider font-medium">High Priority</p>
                  </div>
                  <p className="text-2xl font-semibold text-red-700 dark:text-red-300">{highSeverity.length}</p>
                  {highSeverity.length > 0 && (
                    <p className="text-xs text-red-600/80 dark:text-red-400/80 mt-1 truncate">
                      {highSeverity[0].title}
                    </p>
                  )}
                </div>
                <div className="tc-card p-4 border border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/10">
                  <div className="flex items-center gap-2 mb-1">
                    <Clock className="w-3.5 h-3.5 text-amber-500" />
                    <p className="text-xs text-amber-600 dark:text-amber-400 uppercase tracking-wider font-medium">Medium</p>
                  </div>
                  <p className="text-2xl font-semibold text-amber-700 dark:text-amber-300">{mediumSeverity.length}</p>
                </div>
                <div className="tc-card p-4 border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/10">
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 uppercase tracking-wider font-medium">Positive</p>
                  </div>
                  <p className="text-2xl font-semibold text-emerald-700 dark:text-emerald-300">{positiveSeverity.length}</p>
                </div>
              </div>

              {/* Top findings preview */}
              {highSeverity.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium">Top Issues</h3>
                  {highSeverity.slice(0, 3).map((finding, idx) => (
                    <div key={idx} className="tc-card p-4 border border-red-200 dark:border-red-900 bg-red-50/30 dark:bg-red-950/10">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground">{finding.title}</p>
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{finding.finding_text}</p>
                          {finding.value_inr != null && finding.value_inr > 0 && (
                            <p className="text-xs font-semibold text-red-600 dark:text-red-400 mt-1">
                              Value at risk: ₹{finding.value_inr.toLocaleString('en-IN')}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Skills Map Summary */}
              {report.skills_map_summary && (
                <div className="tc-card p-5">
                  <h3 className="text-sm font-medium text-foreground mb-2">Skills Map Insights</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{report.skills_map_summary}</p>
                </div>
              )}

              {/* PDF download */}
              {report.pdf_url && !report.pdf_url.startsWith('local://') && !report.pdf_url.startsWith('gcs_error://') && (
                <a
                  href={report.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="tc-card p-4 flex items-center gap-3 hover:border-primary/40 transition-colors group"
                >
                  <FileText className="w-5 h-5 text-primary group-hover:scale-110 transition-transform" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">Download Full Audit PDF</p>
                    <p className="text-xs text-muted-foreground">Detailed findings with evidence and recommendations</p>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
                </a>
              )}
            </div>
          ) : (
            <div className="tc-card p-10 text-center">
              <FileText className="w-10 h-10 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">No Audit Report Yet</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Start your email audit from the dashboard to generate your Skills Audit Report.
              </p>
              <Button onClick={() => router.push('/dashboard')}>
                Go to Dashboard
              </Button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
