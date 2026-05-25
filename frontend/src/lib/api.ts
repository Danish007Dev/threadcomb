/**
 * ThreadComb API client.
 *
 * All API calls go through the public backend URL defined in env. NextAuth /
 * Emergent Auth session cookie is httpOnly, samesite=none, secure — so we
 * always include credentials.
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

export async function exchangeSession(sessionId: string): Promise<{
  creator: Creator;
  session_token: string;
}> {
  return request('/auth/session', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

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
