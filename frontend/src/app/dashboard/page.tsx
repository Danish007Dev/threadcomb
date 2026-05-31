'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Handshake,
  ReceiptText,
  BarChart3,
  Settings,
  Sparkles,
  ScanSearch,
  LogOut,
  Play,
  Download,
  FileText,
  Shield,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Loader2,
} from 'lucide-react';

import { Button } from '../../components/ui/button';
import { ThreadCombLogo } from '../../components/brand/Logo';
import { getMe, logout, startIngestion, getAuditReport } from '../../lib/api';
import type { Creator } from '../../lib/types';
import type { AuditReport, AuditFinding } from '../../lib/api';
import { cn } from '../../lib/utils';
import { IngestionProgress } from '../../components/ingestion/IngestionProgress';
import { FirstSignalCard } from './components/FirstSignalCard';
import { useIngestionStatus } from '../../hooks/useIngestionStatus';

const NAV = [
  { label: 'Dashboard', Icon: LayoutDashboard, href: '/dashboard', active: true, testId: 'sidebar-link-dashboard' },
  { label: 'Deals', Icon: Handshake, href: '#', active: false, testId: 'sidebar-link-deals' },
  { label: 'Invoices', Icon: ReceiptText, href: '#', active: false, testId: 'sidebar-link-invoices' },
  { label: 'Reports', Icon: BarChart3, href: '#', active: false, testId: 'sidebar-link-reports' },
  { label: 'Settings', Icon: Settings, href: '#', active: false, testId: 'sidebar-link-settings' },
];

type DashboardState = 'no_gmail' | 'ready' | 'running' | 'complete';

const SEVERITY_CONFIG: Record<string, { color: string; bgColor: string; Icon: typeof AlertTriangle }> = {
  high: { color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-900', Icon: AlertTriangle },
  medium: { color: 'text-amber-600 dark:text-amber-400', bgColor: 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900', Icon: AlertTriangle },
  low: { color: 'text-blue-600 dark:text-blue-400', bgColor: 'bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900', Icon: TrendingUp },
  positive: { color: 'text-emerald-600 dark:text-emerald-400', bgColor: 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900', Icon: CheckCircle2 },
};

export default function DashboardPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [auditStarting, setAuditStarting] = useState(false);
  const [auditReport, setAuditReport] = useState<AuditReport | null>(null);
  const [dashboardState, setDashboardState] = useState<DashboardState>('no_gmail');

  // SSE hook — only active when audit is running
  const { events, latestEvent, isConnected } = useIngestionStatus(
    dashboardState === 'running' ? creator?.creator_id : undefined,
    jobId || undefined
  );

  // Extract first_signal from SSE events
  const firstSignal = useMemo(() => {
    const signalEvent = events.find(e => e.event === 'first_signal');
    if (!signalEvent) return null;
    return {
      title: signalEvent.title || '',
      message: signalEvent.message || '',
      detail: signalEvent.detail || '',
      sub_detail: signalEvent.sub_detail || '',
      deal_count: signalEvent.deal_count || 0,
    };
  }, [events]);

  // Detect audit_complete event
  useEffect(() => {
    const completeEvent = events.find(e => e.event === 'audit_complete');
    if (completeEvent && creator) {
      // Fetch the audit report
      getAuditReport(creator.creator_id)
        .then(report => {
          setAuditReport(report);
          setDashboardState('complete');
        })
        .catch(() => {
          // If report isn't ready yet, try again in a few seconds
          setTimeout(() => {
            if (creator) {
              getAuditReport(creator.creator_id)
                .then(report => {
                  setAuditReport(report);
                  setDashboardState('complete');
                })
                .catch(() => {});
            }
          }, 5000);
        });
    }
  }, [events, creator]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) {
          setCreator(me);
          // If onboarding isn't complete, send them back to the right step.
          if ((me.onboarding_step ?? 0) < 5) {
            if (me.onboarding_step === 0) router.replace('/onboarding/step-1-platform');
            else if (me.onboarding_step === 1) router.replace('/onboarding/step-2-niche');
            else if (me.onboarding_step === 2) router.replace('/onboarding/step-3-profile');
            else router.replace('/onboarding/step-4-connect');
            return;
          }
          // Determine dashboard state
          if (me.gmail_connected) {
            // Check if there's an existing audit report
            try {
              const report = await getAuditReport(me.creator_id);
              setAuditReport(report);
              setDashboardState('complete');
            } catch {
              setDashboardState('ready');
            }
          } else {
            setDashboardState('no_gmail');
          }
        }
      } catch {
        if (!cancelled) router.replace('/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      /* ignore */
    } finally {
      router.replace('/login');
    }
  };

  const handleStartAudit = async () => {
    setAuditStarting(true);
    try {
      const result = await startIngestion();
      setJobId(result.job_id);
      setDashboardState('running');
    } catch (err) {
      console.error('Failed to start audit:', err);
    } finally {
      setAuditStarting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background flex" data-testid="dashboard-layout">
      {/* Sidebar */}
      <aside
        className="hidden md:flex w-60 shrink-0 flex-col border-r border-border/40 bg-card/60 backdrop-blur-sm"
        data-testid="sidebar-nav"
      >
        <div className="px-6 py-6 border-b border-border/40">
          <ThreadCombLogo className="text-primary" />
        </div>
        <nav className="flex-1 px-3 py-5 space-y-1">
          {NAV.map(({ label, Icon, href, active, testId }) => (
            <a
              key={label}
              href={href}
              data-testid={testId}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                active
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </a>
          ))}
        </nav>
        <div className="px-3 pb-6">
          <button
            type="button"
            onClick={handleLogout}
            data-testid="sidebar-logout-btn"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Log out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-6 md:px-10 py-5 border-b border-border/40 bg-background/80 backdrop-blur-sm">
          <div className="md:hidden">
            <ThreadCombLogo className="text-primary" />
          </div>
          <div className="hidden md:block">
            <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              Dashboard
            </span>
          </div>
          <div className="flex items-center gap-3" data-testid="header-avatar">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-foreground leading-tight">
                {creator?.name || 'Creator'}
              </p>
              <p className="text-xs text-muted-foreground leading-tight">{creator?.email}</p>
            </div>
            {creator?.avatar_url ? (
              <img
                src={creator.avatar_url}
                alt={creator.name || 'avatar'}
                className="w-10 h-10 rounded-full object-cover border border-border/60"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-medium">
                {(creator?.name || creator?.email || 'C').charAt(0).toUpperCase()}
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 px-6 py-8 md:px-10 tc-grain overflow-y-auto">
          {/* State 1: No Gmail connected */}
          {dashboardState === 'no_gmail' && (
            <div className="flex items-center justify-center min-h-[60vh]">
              <div
                className="tc-card max-w-xl w-full p-10 md:p-12 text-center"
                data-testid="empty-state-card"
              >
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-accent text-accent-foreground mb-6">
                  <ScanSearch className="w-6 h-6" />
                </div>
                <h2 className="font-heading text-3xl md:text-4xl tracking-tight font-medium text-foreground leading-tight">
                  Connect Gmail to get started.
                </h2>
                <p className="mt-4 text-sm md:text-base text-muted-foreground leading-relaxed">
                  ThreadComb reads your brand deal emails to build your Skills Audit.
                  Connect your Gmail to begin.
                </p>
                <div className="mt-8">
                  <Button
                    disabled
                    size="lg"
                    data-testid="start-audit-btn-disabled"
                    title="Connect Gmail first."
                    className="h-12 px-7"
                  >
                    Start Your Audit
                  </Button>
                  <p className="text-xs text-muted-foreground mt-3">
                    Gmail connection is set up during onboarding.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* State 2: Gmail connected, audit not started */}
          {dashboardState === 'ready' && (
            <div className="flex items-center justify-center min-h-[60vh]">
              <div
                className="tc-card max-w-xl w-full p-10 md:p-12 text-center"
                data-testid="ready-state-card"
              >
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-primary/10 text-primary mb-6">
                  <ScanSearch className="w-6 h-6" />
                </div>
                <h2 className="font-heading text-3xl md:text-4xl tracking-tight font-medium text-foreground leading-tight">
                  We&apos;re ready to read your threads.
                </h2>
                <p className="mt-4 text-sm md:text-base text-muted-foreground leading-relaxed">
                  Your 30-day Skills Audit will show you:
                </p>
                <ul className="mt-4 space-y-2 text-sm text-muted-foreground text-left max-w-md mx-auto">
                  <li className="flex items-start gap-3">
                    <Sparkles className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                    <span>Every brand deal you missed or left unanswered.</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Sparkles className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                    <span>Every overdue invoice and what to say to recover it.</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Sparkles className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                    <span>What you should be charging compared to creators like you.</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Sparkles className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                    <span>Your operational DNA — how you negotiate, what you prefer, who you trust.</span>
                  </li>
                </ul>
                <div className="mt-8">
                  <Button
                    size="lg"
                    data-testid="start-audit-btn"
                    className="h-12 px-7"
                    onClick={handleStartAudit}
                    disabled={auditStarting}
                  >
                    {auditStarting ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Starting...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 mr-2" />
                        Start Your Audit
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* State 3: Audit running */}
          {dashboardState === 'running' && creator && jobId && (
            <div className="max-w-2xl mx-auto space-y-4">
              <FirstSignalCard signal={firstSignal} />
              <IngestionProgress
                creatorId={creator.creator_id}
                jobId={jobId}
              />
            </div>
          )}

          {/* State 4: Audit complete */}
          {dashboardState === 'complete' && auditReport && (
            <div className="max-w-3xl mx-auto space-y-6">
              {/* Executive Summary Card */}
              <div className="tc-card p-6 md:p-8">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Skills Audit</p>
                    <h2 className="font-heading text-2xl md:text-3xl text-foreground mt-2">
                      Your Audit Report
                    </h2>
                  </div>
                  {auditReport.pdf_url && !auditReport.pdf_url.startsWith('local://') && !auditReport.pdf_url.startsWith('gcs_error://') && (
                    <a
                      href={auditReport.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
                      data-testid="download-pdf-btn"
                    >
                      <Download className="w-4 h-4" />
                      Download PDF
                    </a>
                  )}
                </div>
                <p className="text-sm md:text-base text-muted-foreground leading-relaxed">
                  {auditReport.executive_summary}
                </p>
                {auditReport.total_recoverable_value != null && auditReport.total_recoverable_value > 0 && (
                  <div className="mt-4 p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <p className="text-xs uppercase tracking-wider text-primary font-semibold">Recoverable Value</p>
                    <p className="text-2xl font-bold text-foreground mt-1">
                      ₹{auditReport.total_recoverable_value.toLocaleString('en-IN')}
                    </p>
                  </div>
                )}
                {auditReport.total_recoverable_unknown && !auditReport.total_recoverable_value && (
                  <div className="mt-4 p-4 rounded-lg bg-muted border border-border/40">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Recoverable Value</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Unknown — deal amounts not stated in emails. Deal count tracked in findings below.
                    </p>
                  </div>
                )}
              </div>

              {/* Findings */}
              {auditReport.findings.map((finding, idx) => {
                const config = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.low;
                const FindingIcon = config.Icon;
                return (
                  <div
                    key={idx}
                    className={cn('tc-card p-5 md:p-6 border', config.bgColor)}
                    data-testid={`finding-card-${idx}`}
                  >
                    <div className="flex items-start gap-3">
                      <FindingIcon className={cn('w-5 h-5 mt-0.5 shrink-0', config.color)} />
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
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
                        <div className="text-xs text-muted-foreground space-y-1 pt-1 border-t border-border/30">
                          <p><span className="font-medium">Evidence:</span> {finding.evidence}</p>
                          <p><span className="font-medium">Recommendation:</span> {finding.recommendation}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Skills Map Summary */}
              {auditReport.skills_map_summary && (
                <div className="tc-card p-6 md:p-8">
                  <div className="flex items-center gap-3 mb-3">
                    <Shield className="w-5 h-5 text-primary" />
                    <h3 className="font-heading text-lg text-foreground">Your Operational DNA</h3>
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {auditReport.skills_map_summary}
                  </p>
                </div>
              )}

              {/* Data Quality Note */}
              {auditReport.data_quality_note && (
                <div className="tc-card p-5 border border-border/40">
                  <div className="flex items-center gap-3 mb-2">
                    <FileText className="w-4 h-4 text-muted-foreground" />
                    <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
                      Note on Data Quality
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {auditReport.data_quality_note}
                  </p>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
