'use client';

import { Button } from '../../components/ui/button';
import { ThreadCombLogo } from '../../components/brand/Logo';
import { LogIn, ShieldCheck, Sparkles, Inbox } from 'lucide-react';
import { API_BASE } from '../../lib/api';
import { ThemeToggle } from '../../components/ThemeToggle';
import Link from 'next/link';

/**
 * Login page — split layout: brand pitch on the left, abstract artwork on the right.
 *
 * Google OAuth login. The backend handles the code exchange and sets the
 * session cookie before redirecting back to the app.
 */
export default function LoginPage() {
  const handleLogin = () => {
    const nextUrl = `${window.location.origin}/auth/callback`;
    window.location.href = `${API_BASE}/auth/google/login?next=${encodeURIComponent(nextUrl)}`;
  };

  return (
    <div
      className="min-h-dvh grid md:grid-cols-2 bg-background"
      data-testid="login-page-container"
    >
      {/* Left pane — pitch + sign-in */}
      <div className="flex flex-col px-8 py-10 md:px-16 md:py-14 lg:px-24">
        <div className="flex items-center justify-between">
          <ThreadCombLogo data-testid="login-logo" className="text-primary" />
          <ThemeToggle />
        </div>

        <div className="flex-1 flex flex-col justify-center max-w-xl mt-12 md:mt-0">
          <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground mb-5">
            For creators in India
          </span>

          <h1
            data-testid="login-title"
            className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tight font-medium leading-[1.05] text-foreground"
          >
            Every brand deal lives in a thread.
            <span className="block text-primary mt-2">ThreadComb reads them all.</span>
          </h1>

          <p className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed max-w-lg">
            Three TC's agents read your Gmail brand deal history, build your operational DNA,
            and draft replies in your voice while keeping you in full control.
          </p>

          <div className="mt-10 flex flex-col gap-4 max-w-md">
            <Button
              size="lg"
              onClick={handleLogin}
              data-testid="login-google-btn"
              className="h-12 text-base"
            >
              <LogIn className="w-4 h-4" />
              Continue with Google
            </Button>
            <p className="text-xs text-muted-foreground">
              We use Google sign-in to verify it&apos;s you. We never read your password.
            </p>
          </div>

          <div className="mt-14 grid grid-cols-1 sm:grid-cols-3 gap-5 max-w-xl">
            <div className="flex flex-col gap-2">
              <Inbox className="w-5 h-5 text-primary" />
              <span className="text-sm font-medium text-foreground">Reads brand emails</span>
              <span className="text-xs text-muted-foreground leading-snug">
                Builds your Skills Map from real deals.
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              <span className="text-sm font-medium text-foreground">Drafts in your voice</span>
              <span className="text-xs text-muted-foreground leading-snug">
                One-tap approval. Never sends without you.
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <ShieldCheck className="w-5 h-5 text-primary" />
              <span className="text-sm font-medium text-foreground">DPDP-aware</span>
              <span className="text-xs text-muted-foreground leading-snug">
                Email text is never stored. Only structured signals.
              </span>
            </div>
          </div>
        </div>

        <div className="text-xs text-muted-foreground pt-10 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
          <span>© {new Date().getFullYear()} ThreadComb</span>
          <div className="flex items-center gap-3">
            <Link href="/privacy" className="hover:text-foreground transition-colors underline underline-offset-2">Privacy Policy</Link>
            <Link href="/terms" className="hover:text-foreground transition-colors underline underline-offset-2">Terms of Service</Link>
          </div>
        </div>
      </div>

      {/* Right pane — abstract artwork */}
      <div className="relative hidden md:block overflow-hidden bg-primary tc-grain">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.16),transparent_22%),radial-gradient(circle_at_80%_70%,rgba(255,255,255,0.14),transparent_18%),linear-gradient(135deg,rgba(12,71,57,0.94),rgba(24,96,79,0.92))]" />
        <div className="absolute inset-0 opacity-70 bg-[linear-gradient(120deg,transparent_0%,rgba(255,255,255,0.06)_50%,transparent_100%)]" />
        <div className="absolute bottom-10 left-10 right-10 text-primary-foreground">
          <p className="text-sm font-medium uppercase tracking-[0.18em] opacity-80">
            What you&apos;ll see first
          </p>
          <p className="font-heading text-2xl lg:text-3xl mt-3 leading-tight">
            A 30-day Skills Audit showing exactly what revenue you&apos;ve been leaving on the table.
          </p>
        </div>
      </div>
    </div>
  );
}
