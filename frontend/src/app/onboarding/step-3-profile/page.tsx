'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { ArrowLeft, ArrowRight } from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select';

import { StepIndicator } from '../../../components/onboarding/StepIndicator';
import { useOnboarding } from '../../../store/onboarding';
import { patchStep3 } from '../../../lib/api';
import type { FollowerBucket } from '../../../lib/types';

const FOLLOWER_OPTIONS: Array<{ value: FollowerBucket; label: string }> = [
  { value: 'under_10k', label: 'Under 10K' },
  { value: '10k_50k', label: '10K – 50K' },
  { value: '50k_200k', label: '50K – 200K' },
  { value: '200k_1m', label: '200K – 1M' },
  { value: 'over_1m', label: 'Over 1M' },
];

const GEOGRAPHIES = [
  { value: 'IN', label: 'India' },
  { value: 'AE', label: 'UAE' },
  { value: 'GB', label: 'United Kingdom' },
  { value: 'US', label: 'United States' },
  { value: 'SG', label: 'Singapore' },
  { value: 'OTHER', label: 'Other' },
];

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'hi-en', label: 'Hindi + English mix' },
  { value: 'other', label: 'Other' },
];

export default function Step3ProfilePage() {
  const router = useRouter();
  const creator = useOnboarding((s) => s.creator);
  const handle = useOnboarding((s) => s.handle);
  const setHandle = useOnboarding((s) => s.setHandle);
  const followerBucket = useOnboarding((s) => s.followerBucket);
  const setFollowerBucket = useOnboarding((s) => s.setFollowerBucket);
  const geography = useOnboarding((s) => s.geography);
  const setGeography = useOnboarding((s) => s.setGeography);
  const languagePrimary = useOnboarding((s) => s.languagePrimary);
  const setLanguagePrimary = useOnboarding((s) => s.setLanguagePrimary);

  const [submitting, setSubmitting] = useState(false);

  const handleNext = async () => {
    if (!followerBucket || !creator) {
      toast.error('Pick your follower bucket to continue.');
      return;
    }
    setSubmitting(true);
    try {
      await patchStep3(creator.creator_id, {
        handle: handle || null,
        follower_bucket: followerBucket,
        geography,
        language_primary: languagePrimary,
      });
      router.push('/onboarding/step-4-connect');
    } catch (err: any) {
      toast.error(err?.message || 'Could not save your profile.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto" data-testid="onboarding-step-3">
      <div className="mb-10">
        <StepIndicator currentStep={3} />
      </div>

      <div className="mb-10">
        <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Step 3 of 4
        </span>
        <h1 className="font-heading text-4xl sm:text-5xl tracking-tight font-medium text-foreground leading-none mt-3">
          Weave your profile.
        </h1>
        <p className="text-base text-muted-foreground mt-4 max-w-2xl">
          Helps ThreadComb benchmark your rates against creators just like you.
        </p>
      </div>

      <div className="tc-card p-7 md:p-10 space-y-7" data-testid="profile-form-card">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-7">
          <div className="space-y-2">
            <Label htmlFor="handle">Instagram or YouTube handle</Label>
            <Input
              id="handle"
              data-testid="profile-handle-input"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              placeholder="@yourhandle"
            />
            <p className="text-xs text-muted-foreground">Optional — without the @ works too.</p>
          </div>

          <div className="space-y-2">
            <Label>Follower count</Label>
            <Select
              value={followerBucket ?? undefined}
              onValueChange={(v) => setFollowerBucket(v as FollowerBucket)}
            >
              <SelectTrigger data-testid="profile-followers-select">
                <SelectValue placeholder="Pick a range" />
              </SelectTrigger>
              <SelectContent>
                {FOLLOWER_OPTIONS.map((opt) => (
                  <SelectItem
                    key={opt.value}
                    value={opt.value}
                    data-testid={`profile-followers-option-${opt.value}`}
                  >
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Geography</Label>
            <Select value={geography} onValueChange={setGeography}>
              <SelectTrigger data-testid="profile-geo-select">
                <SelectValue placeholder="Where you create from" />
              </SelectTrigger>
              <SelectContent>
                {GEOGRAPHIES.map((g) => (
                  <SelectItem key={g.value} value={g.value}>
                    {g.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Primary language</Label>
            <Select value={languagePrimary} onValueChange={setLanguagePrimary}>
              <SelectTrigger data-testid="profile-lang-select">
                <SelectValue placeholder="Pick your language" />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((lang) => (
                  <SelectItem key={lang.value} value={lang.value}>
                    {lang.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between flex-wrap gap-4">
        <Button
          variant="ghost"
          onClick={() => router.push('/onboarding/step-2-niche')}
          data-testid="step-3-back-btn"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <Button
          onClick={handleNext}
          disabled={submitting}
          size="lg"
          data-testid="step-3-next-btn"
        >
          Continue
          <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
