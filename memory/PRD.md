# ThreadComb — PRD

## Original Problem Statement
**ThreadComb** — AI-powered creator operations platform for mid-tier Indian creators (15K–200K followers).
Tagline: *Every brand deal lives in a thread. ThreadComb reads them all.*

Three AI agents (DNA Reader, Deal Chief, Revenue Guardian) read a creator's Gmail brand-deal history,
build a MongoDB Skills Map, then draft/recover/audit — always with creator approval before any
irreversible action.

## Architecture

- **Frontend:** Next.js 15 (App Router, TypeScript) + Tailwind + shadcn/ui + Zustand
- **Backend:** FastAPI + Pydantic v2 + Motor (async MongoDB)
- **Database:** MongoDB (local in dev; Atlas in prod) — 10 spec collections + creator_sessions
- **Auth:** Emergent-managed Google Auth (httpOnly cookie, 7-day session)
- **LLM (future sessions):** Gemini via Emergent Universal LLM key
- **Storage (future):** Google Cloud Storage for Audit Report PDFs
- **Queue (future):** Google Cloud Tasks for background ingestion

## User Personas
1. **Mid-tier Indian creator (15K–200K followers)** — primary persona. Beauty / gaming / finance /
   education / food / tech / fashion niches. Wants to recover unanswered deals + chase invoices
   without manually trawling Gmail.
2. **Pilot creator (Day 1–18 testing)** — uses ThreadComb against real Gmail; provides voice
   calibration feedback.

## Core Non-Negotiable Principles (encoded in code)
1. Human approval before irreversible action.
2. ACTION_POLICY is Python code at `backend/services/action_policy.py`, not a prompt.
3. Raw email text never touches persistent storage.
4. Every Mongo write includes `data_classification` (enforced via `write_with_classification`).
5. Ambiguous amounts (e.g., "50 hazaar") never auto-populate; flagged for HITL.
6. Draft generation and voice evaluation are separate model calls (Session 5).

## Session 1 — DONE (2026-05-25)

Built the foundation:
- Next.js 15 App Router + TypeScript scaffold (replaced CRA)
- FastAPI backend with mongo singleton + startup hooks
- All 10 spec collections + `creator_sessions` for Emergent Auth
- Indexes on `creator_id`, `email`, `google_sub`, `domain`, `(creator_id, status)`, etc.
- ACTION_POLICY table (3 buckets: always-require / default-require / HITL-by-confidence)
- `write_with_classification()` chokepoint — verified via testing agent (zero direct inserts elsewhere)
- Login page (Emergent Google Auth redirect)
- 4-step onboarding (Platform / Niche / Profile / Gmail-Connect-mocked)
- Empty-state dashboard with sidebar nav
- `niche_graph` pre-training seed: 10 docs (beauty/gaming/finance/education/fashion/tech/food/wellness)
- Standalone `python backend/database/run_seed.py` script
- DPDP-compliant `DELETE /api/auth/creator/{id}` cascading across collections
- Premium UI: Outfit/Figtree fonts, organic earthy palette, lucide icons (no emojis)
- 22/22 backend pytest tests pass; all 7 frontend pages verified

## Prioritized Backlog

### P0 — Session 2 (Gmail OAuth real)
- Replace mocked Gmail connect with real Google OAuth handshake using `GMAIL_CLIENT_ID/SECRET`.
- Store refresh token in Google Secret Manager; record only the path on `creators.gmail_secret_path`.
- Wire up Gmail watch / push notifications via Pub/Sub topic.
- Begin Cloud Tasks queue setup for background ingestion.

### P0 — Session 3 (DNA Reader)
- Gmail message fetch + brand-thread classifier (Gemini 2.5 Flash Lite gate).
- Per-thread extraction (Gemini 2.5 Flash) producing `Deal` documents.
- Brand upsert with `PaymentIntelligence` / `DealIntelligence`.
- Skills Map synthesis (Gemini 2.5 Pro) → `skills_map` nodes with evidence decay.
- 30-day Audit Report PDF → GCS.
- Atlas Vector Search index on `embedding_vector` (manual Atlas UI step).
- Wire up the `Start Your Audit` CTA on the dashboard.

### P1 — Session 4 (Deal Chief)
- Contract extraction & risk scoring (`ContractExtraction`).
- Draft brand-deal replies in creator voice (two separate calls per Principle 6).
- One-tap approval inbox UI.

### P1 — Session 5 (Revenue Guardian + Fan Manager)
- Invoice overdue tracker + tone-calibrated follow-up drafts.
- Fan reply templates with auto-approval gating (`response_templates`).
- Fan interactions ingestion.

### P2
- Settings UI for `auto_approve_*` toggles per ACTION_POLICY.
- Anonymisation pipeline to populate Layer 2 `niche_graph` from real creator data.
- Pilot expiry handling & subscription paywall.
- Mobile-responsive sidebar.

## Files of Record
- `/app/backend/server.py` — FastAPI entry
- `/app/backend/services/action_policy.py` — Policy table
- `/app/backend/services/mongodb_writer.py` — Write chokepoint
- `/app/backend/database/seed.py`, `run_seed.py` — Seed + standalone exec
- `/app/backend/routers/{auth,onboarding,health}.py`
- `/app/backend/models/{common,creator,deal,contract}.py`
- `/app/frontend/src/app/{login,auth/callback,onboarding/*,dashboard}/page.tsx`
- `/app/frontend/src/lib/{api.ts,types.ts}` — API client + types
- `/app/frontend/src/store/onboarding.ts` — Zustand
- `/app/backend/tests/test_threadcomb_session1.py` — Regression baseline
