'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Check,
  X,
  Mail,
  ShieldCheck,
  Lock,
  ScrollText,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { StepIndicator } from '../../../components/onboarding/StepIndicator';
import { useOnboarding } from '../../../store/onboarding';
import { connectGmail } from '../../../lib/api';

const WILL_READ = [
  'Emails about brand deals, sponsorships, and partnerships',
  'Emails containing invoices or payment requests',
  'Emails about contracts or collaboration agreements',
  'Emails from brands about gifting or PR packages',
];

const NEVER_READ = [
  'Personal emails (family, friends)',
  'Shopping receipts or subscriptions',
  'Social media notifications',
  'Any email unrelated to your creator business',
];

const DATA_PROTECTION = [
  'Email text is processed in memory and immediately discarded — never saved.',
  'Only structured data (deal amounts, brand names, dates) is stored.',
  'You can disconnect and delete all data at any time from Settings.',
];

export default function Step4ConnectPage() {
  const router = useRouter();
  const creator = useOnboarding((s) => s.creator);
  const [submitting, setSubmitting] = useState(false);

  const handleConnect = async () => {
    if (!creator) return;
    setSubmitting(true);
    try {
      // SESSION 1: Gmail OAuth is mocked. We immediately mark the creator as
      // connected and finish onboarding. Real OAuth ships in Session 2.
      await connectGmail(creator.creator_id);
      toast.success('Gmail connected. Welcome to ThreadComb.');
      router.push('/dashboard');
    } catch (err: any) {
      toast.error(err?.message || 'Could not connect Gmail.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto" data-testid="onboarding-step-4">
      <div className="mb-10">
        <StepIndicator currentStep={4} />
      </div>

      <div className="mb-10">
        <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Step 4 of 4
        </span>
        <h1 className="font-heading text-4xl sm:text-5xl tracking-tight font-medium text-foreground leading-none mt-3">
          Authorize your ThreadComb.
        </h1>
        <p className="text-base text-muted-foreground mt-4 max-w-2xl">
          ThreadComb needs <span className="font-medium text-foreground">read-only</span> access
          to your Gmail to read brand deal threads. Below is everything we will — and will not — touch.
        </p>
      </div>

      {/* Section A — Will read */}
      <div
        className="tc-card p-6 md:p-8 mb-5"
        style={{
          backgroundColor: 'hsl(135 25% 96%)',
          borderColor: 'hsl(140 30% 80%)',
        }}
        data-testid="trust-will-read-card"
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'hsl(140 35% 88%)', color: 'hsl(140 60% 22%)' }}
          >
            <Mail className="w-4 h-4" />
          </div>
          <h2 className="font-heading text-lg md:text-xl font-medium" style={{ color: 'hsl(140 60% 18%)' }}>
            What ThreadComb will read
          </h2>
        </div>
        <ul className="space-y-3">
          {WILL_READ.map((item) => (
            <li key={item} className="flex items-start gap-3 text-sm" style={{ color: 'hsl(140 40% 22%)' }}>
              <Check
                className="w-4 h-4 mt-0.5 shrink-0"
                style={{ color: 'hsl(140 55% 32%)' }}
                aria-hidden="true"
              />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Section B — Never read */}
      <div
        className="tc-card p-6 md:p-8 mb-5"
        style={{
          backgroundColor: 'hsl(10 50% 96%)',
          borderColor: 'hsl(10 45% 82%)',
        }}
        data-testid="trust-never-read-card"
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'hsl(10 55% 90%)', color: 'hsl(10 60% 35%)' }}
          >
            <X className="w-4 h-4" />
          </div>
          <h2 className="font-heading text-lg md:text-xl font-medium" style={{ color: 'hsl(10 60% 28%)' }}>
            What ThreadComb will NEVER read
          </h2>
        </div>
        <ul className="space-y-3">
          {NEVER_READ.map((item) => (
            <li key={item} className="flex items-start gap-3 text-sm" style={{ color: 'hsl(10 35% 25%)' }}>
              <X
                className="w-4 h-4 mt-0.5 shrink-0"
                style={{ color: 'hsl(10 55% 45%)' }}
                aria-hidden="true"
              />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Section C — Data protection */}
      <div className="tc-card p-6 md:p-8 mb-8" data-testid="data-protection-list">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-accent text-accent-foreground">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <h2 className="font-heading text-lg md:text-xl font-medium text-foreground">
            Your data is protected
          </h2>
        </div>
        <ul className="space-y-3">
          {DATA_PROTECTION.map((item, idx) => (
            <li key={item} className="flex items-start gap-3 text-sm text-muted-foreground">
              {idx === 0 && <Lock className="w-4 h-4 mt-0.5 text-primary shrink-0" />}
              {idx === 1 && <ScrollText className="w-4 h-4 mt-0.5 text-primary shrink-0" />}
              {idx === 2 && <ShieldCheck className="w-4 h-4 mt-0.5 text-primary shrink-0" />}
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-4">
        <Button
          variant="ghost"
          onClick={() => router.push('/onboarding/step-3-profile')}
          data-testid="step-4-back-btn"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <Button
          onClick={handleConnect}
          disabled={submitting}
          size="lg"
          data-testid="connect-gmail-btn"
          className="h-12 px-7 text-base"
        >
          <Mail className="w-4 h-4" />
          Connect Gmail — Read Only Access
        </Button>
      </div>

      <p className="text-[11px] text-muted-foreground mt-4 text-right">
        Scope requested: <code className="font-mono">https://www.googleapis.com/auth/gmail.readonly</code>
      </p>
    </div>
  );
}
