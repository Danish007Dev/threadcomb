'use client';

import { useEffect, useState } from 'react';
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
} from 'lucide-react';

import { Button } from '../../components/ui/button';
import { ThreadCombLogo } from '../../components/brand/Logo';
import { getMe, logout } from '../../lib/api';
import type { Creator } from '../../lib/types';
import { cn } from '../../lib/utils';

const NAV = [
  { label: 'Dashboard', Icon: LayoutDashboard, href: '/dashboard', active: true, testId: 'sidebar-link-dashboard' },
  { label: 'Deals', Icon: Handshake, href: '#', active: false, testId: 'sidebar-link-deals' },
  { label: 'Invoices', Icon: ReceiptText, href: '#', active: false, testId: 'sidebar-link-invoices' },
  { label: 'Reports', Icon: BarChart3, href: '#', active: false, testId: 'sidebar-link-reports' },
  { label: 'Settings', Icon: Settings, href: '#', active: false, testId: 'sidebar-link-settings' },
];

export default function DashboardPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);

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

        <main className="flex-1 flex items-center justify-center px-6 py-14 tc-grain">
          <div
            className="tc-card max-w-xl w-full p-10 md:p-12 text-center"
            data-testid="empty-state-card"
          >
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-accent text-accent-foreground mb-6">
              <ScanSearch className="w-6 h-6" />
            </div>
            <h2 className="font-heading text-3xl md:text-4xl tracking-tight font-medium text-foreground leading-tight">
              We&apos;re getting ready to read your threads.
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
                disabled
                size="lg"
                data-testid="start-audit-btn-disabled"
                title="Available in Session 3 once your DNA Reader is online."
                className="h-12 px-7"
              >
                Start Your Audit
              </Button>
              <p className="text-xs text-muted-foreground mt-3">
                Coming soon — the DNA Reader is being calibrated.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
