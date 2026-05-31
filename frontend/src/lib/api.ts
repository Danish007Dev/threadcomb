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
