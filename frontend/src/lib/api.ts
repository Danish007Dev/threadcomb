/**
 * ThreadComb API client.
 *
 * All API calls go through the public backend URL defined in env. We always
 * include credentials so the Google OAuth session cookie is sent.
 */

import type { Creator, Platform, Niche, FollowerBucket } from './types';

const RAW_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  (typeof window !== 'undefined' ? window.location.origin : '');

export const API_BASE = `${RAW_URL.replace(/\/$/, '')}/api`;

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch (_) {
      // ignore JSON parse
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

// ---------- Auth ----------

export async function getMe(): Promise<Creator> {
  return request('/auth/me');
}

export async function logout(): Promise<{ ok: boolean }> {
  return request('/auth/logout', { method: 'POST' });
}

export async function deleteCreator(creatorId: string) {
  return request(`/auth/creator/${creatorId}`, { method: 'DELETE' });
}

// ---------- Onboarding ----------

export async function patchStep1(creatorId: string, platform: Platform) {
  return request<Creator>(`/onboarding/${creatorId}/step-1`, {
    method: 'PATCH',
    body: JSON.stringify({ platform }),
  });
}

export async function patchStep2(
  creatorId: string,
  niche: Niche,
  nicheSecondary: Niche[] = []
) {
  return request<Creator>(`/onboarding/${creatorId}/step-2`, {
    method: 'PATCH',
    body: JSON.stringify({ niche, niche_secondary: nicheSecondary }),
  });
}

export interface Step3Payload {
  handle?: string | null;
  follower_bucket: FollowerBucket;
  geography: string;
  language_primary: string;
}

export async function patchStep3(creatorId: string, payload: Step3Payload) {
  return request<Creator>(`/onboarding/${creatorId}/step-3`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function connectGmail(creatorId: string) {
  return request<Creator>(`/onboarding/${creatorId}/gmail-connect`, {
    method: 'POST',
  });
}

export async function onboardingStatus(creatorId: string) {
  return request<Creator>(`/onboarding/${creatorId}/status`);
}

// ---------- Ingestion (Session 3) ----------

export async function startIngestion() {
  return request<{ job_id: string; sse_channel: string; status: string }>(
    '/ingestion/start',
    { method: 'POST' }
  );
}

export async function triggerDevExtraction(jobId: string) {
  return request<{ status: string; threads_triggered: number; mode: string }>(
    `/ingestion/trigger-dev-extraction/${jobId}`,
    { method: 'POST' }
  );
}

// ---------- Audit (Session 3) ----------

export async function getAuditReport(creatorId: string) {
  return request<AuditReport>(`/audit/report/${creatorId}`);
}

export async function triggerAuditGeneration(creatorId: string) {
  return request<{ status: string; message: string }>(
    `/audit/generate/${creatorId}`,
    { method: 'POST' }
  );
}

// ---------- Types for API responses ----------

export interface AuditFinding {
  section: string;
  title: string;
  severity: 'high' | 'medium' | 'low' | 'positive';
  finding_text: string;
  evidence: string;
  recommendation: string;
  value_inr: number | null;
  value_unknown: boolean;
}

export interface AuditReport {
  _id: string;
  creator_id: string;
  findings: AuditFinding[];
  executive_summary: string;
  total_recoverable_value: number | null;
  total_recoverable_unknown: boolean;
  skills_map_summary: string;
  data_quality_note: string | null;
  pdf_url: string;
  created_at: string;
}

// ---------- Deals (Session 4) ----------

export interface DraftFlag {
  flag_type: string;
  severity: 'high' | 'medium' | 'low';
  message: string;
  recommended_action: string | null;
}

export interface DealDraft {
  _id: string;
  deal_id: string;
  thread_id: string;
  creator_id: string;
  brand_name: string | null;
  brand_domain: string | null;
  brand_reliability_score: number;
  brand_is_new: boolean;
  offered_amount: number | null;
  offered_amount_ambiguous: boolean;
  market_p50: number | null;
  market_p25: number | null;
  market_p75: number | null;
  rate_gap_percentage: number | null;
  benchmark_confidence: number;
  similar_deals_found: number;
  similar_deals_summary: string | null;
  draft_text: string;
  draft_language: string;
  model_used: string;
  voice_compliance_score: number;
  voice_compliance_issues: string[];
  flags: DraftFlag[];
  has_high_severity_flags: boolean;
  generated_at: string;
  generation_latency_ms: number | null;
  creator_action: string | null;
  final_text: string | null;
  sent_at: string | null;
  calendar_event_id: string | null;
}

export interface InboundDeal {
  _id: string;
  creator_id: string;
  brand_id: string | null;
  deal_type: string | null;
  status: string;
  financials: {
    amount: number | null;
    amount_inr: number | null;
    amount_ambiguity_flag: boolean;
    amount_raw_text: string | null;
    currency: string;
    payment_terms: string | null;
  };
  raw_signals: {
    deliverables: string[];
    exclusivity_mentioned: boolean;
    exclusivity_duration_days: number | null;
    brand_contact_email: string | null;
    gmail_thread_id: string;
    is_agency_contact: boolean;
  };
  brand?: {
    name: string;
    domain: string;
    payment_reliability: number;
    avg_payment_days: number | null;
  };
  has_pending_draft: boolean;
  created_at: string;
}

export async function getInboundDeals(): Promise<InboundDeal[]> {
  return request('/deals/inbound');
}

export async function generateDealDraft(dealId: string): Promise<{ status: string; message: string }> {
  return request(`/deals/generate-draft/${dealId}`, { method: 'POST' });
}

export async function getDealDraft(dealId: string): Promise<DealDraft> {
  return request(`/deals/draft/${dealId}`);
}

export async function approveDeal(
  dealId: string,
  finalText: string,
  action: 'approved' | 'edited' = 'approved',
  followUpDays: number = 3,
): Promise<{ status: string; message: string; calendar_event_created: boolean; follow_up_date: string }> {
  return request(`/deals/approve/${dealId}`, {
    method: 'POST',
    body: JSON.stringify({ final_text: finalText, action, follow_up_days: followUpDays }),
  });
}

export async function rejectDeal(dealId: string, reason: string = ''): Promise<{ status: string; message: string }> {
  return request(`/deals/reject/${dealId}`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

// ---------- Guardian / Invoices (Session 5) ----------

export interface InvoiceFollowupDraft {
  invoice_id: string;
  brand_name: string;
  amount_inr: number;
  days_overdue: number;
  tone: string;
  draft_text: string;
  creator_action?: string | null;
  sent_at?: string | null;
}

export interface PendingFollowups {
  _id: string;
  creator_id: string;
  run_date: string;
  drafts: InvoiceFollowupDraft[];
  total_overdue: number;
  total_sent?: number;
}

export async function getGuardianPending(): Promise<PendingFollowups> {
  return request('/guardian/pending');
}

export async function triggerGuardianRun(): Promise<{ status: string; message: string }> {
  return request('/guardian/run', { method: 'POST' });
}

export async function approveFollowupBatch(
  approvedIds: string[],
  skippedIds: string[] = []
): Promise<{ status: string; sent: number; skipped: number }> {
  return request('/guardian/approve-batch', {
    method: 'POST',
    body: JSON.stringify({
      approved_invoice_ids: approvedIds,
      skipped_invoice_ids: skippedIds,
    }),
  });
}

export async function approveSingleFollowup(
  invoiceId: string,
  finalText?: string
): Promise<{ status: string; invoice_id: string }> {
  return request(`/guardian/approve-single/${invoiceId}`, {
    method: 'POST',
    body: JSON.stringify({ final_text: finalText || null }),
  });
}

// ---------- Settings (Session 5) ----------

export async function exportSkillsMap(): Promise<Blob> {
  const res = await fetch(`${API_BASE}/settings/export`, {
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

export async function deleteAccount(): Promise<{ status: string; message: string; deletion_counts: Record<string, number> }> {
  return request('/settings/delete-account', { method: 'DELETE' });
}

