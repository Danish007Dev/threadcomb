# ThreadComb

<div align="center">

**Every brand deal lives in a thread. ThreadComb reads them all.**

[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-00ED64?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Google ADK](https://img.shields.io/badge/Google_Cloud-ADK-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com)
[![Vertex AI](https://img.shields.io/badge/Vertex_AI-Production-EA4335?style=for-the-badge&logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![Gemini 2.5](https://img.shields.io/badge/Gemini-2.5-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=nextdotjs)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.11-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[Live Demo](https://threadcomb.com) · [Demo Video](https://youtu.be/1u-ti2y5TOk) 

</div>

---

## What is ThreadComb?

ThreadComb is a **three-agent AI system** built on **Google Cloud Agent Development Kit (ADK)** and **MongoDB Atlas** that replaces the entire operational layer of a content creator's brand deal business. It connects to a creator's Gmail, reads their brand deal history, builds a living knowledge graph — the **Skills Map** — in MongoDB Atlas, and then acts autonomously: detecting inbound deals, drafting replies in the creator's own voice, and chasing overdue payments.

**Not a tool that helps creators do the work. A system that does the work.**

| Without ThreadComb | With ThreadComb |
|---|---|
| Miss brand deal emails buried in inbox chaos | **DNA Reader** detects every deal signal within 30s of arrival via Gmail push |
| Spend 45 minutes researching history and drafting a reply | **Deal Chief** generates a voice-calibrated, historically grounded reply in 60s |
| Chase unpaid invoices awkwardly with no tracking system | **Revenue Guardian** computes urgency scores in MongoDB and sends tone-calibrated follow-ups |

---

## The Problem — Real Numbers

India has over **3 million mid-tier creators** (15K–200K followers) who earn substantial income from brand partnerships but have zero professional operations infrastructure. A creator with 80K Instagram followers can earn ₹60 lakh/year from brand deals — yet they spend 12+ hours/week managing them manually. No agency will sign them. No product does the work for them.

In our pilot:
- Average creator left **₹2.25 lakh in unanswered brand deal emails** over 6 months
- Average brand invoice was **47 days overdue** with zero follow-up
- **0 out of 10 creators** had any system for tracking what brands owed them

---

## The Three Agents

### Agent 1 — DNA Reader (Ingestion & Audit)

**Trigger:** Creator clicks "Start Audit" or new email arrives via Gmail Pub/Sub push notification.

**Pipeline (10 steps):**

```
Gmail API (6 months of threads)
    │
    ▼ Email Sanitiser (in-memory only — raw text is NEVER persisted)
    │  Strips signatures, HTML, PII (phone/address regex)
    │  Handles multipart/alternative MIME parsing
    │
    ▼ Deterministic Spam Check (zero LLM cost)
    │  17 known spam signals checked before any API call
    │  Token-length floor: threads < 50 tokens skipped
    │
    ▼ Stage 0: Gemini Flash-Lite Gate Classifier
    │  Binary: brand deal signal? spam? Hindi-mixed?
    │  Confidence < 0.60 → routed to HITL queue (not MongoDB)
    │
    ▼ Gemini Flash Structured Extraction
    │  Schema: DealExtraction (40+ fields, Pydantic v2 enforced)
    │  Uses response_schema=DealExtraction for guaranteed JSON
    │  CRITICAL: amount_ambiguity_flag=true → all amount fields = None
    │  "50 hazaar", "budget flexible" → flagged. "₹50,000" → extracted.
    │
    ▼ gemini-embedding-2-preview @ 768 dimensions
    │  task_type=RETRIEVAL_DOCUMENT (index time)
    │  L2 normalisation applied (768d is NOT pre-normalised by API)
    │  Stored in deals.embedding_vector → Atlas Vector Search
    │
    ▼ MongoDB Writes
    │  deals.insert_one() — full deal document with embedding
    │  brands.update_one($inc total_deals) — running payment intelligence
    │  skills_map.update_one($inc evidence.count) — preference accumulation
    │  Confidence = min(count/10, 1.0) — preferences expire via decay_rate
    │
    ▼ DLQ (Dead Letter Queue)
    │  Failed extractions retry 3x with exponential backoff
    │  After max retries → quarantined in ingestion_tasks as "dead_letter"
    │
    ▼ 3 MongoDB Aggregation Pipelines (ALL run in MongoDB, not Python)
    │  Pipeline 1: Revenue leakage — unanswered deals × known amounts
    │  Pipeline 2: Payment reliability — brands ranked by paid_count/total_deals
    │  Pipeline 3: Rate gap — creator's avg rate vs niche_graph market P50
    │
    ▼ Gemini 2.5 Pro Synthesis → Audit Report
       Input: SynthesisContext (typed Pydantic — no raw text)
       Output: SynthesisReport (response_schema enforced)
       Falls back to Gemini Flash if Pro quota exhausted
       Rule: If has_estimates=false → "value unknown", never fabricate amounts
       PDF generated via reportlab → uploaded to Google Cloud Storage
```

**Key technical detail:** The extraction worker ([extract_thread.py](file:///d:/Development/HACKATHONS/threadcomb/backend/workers/extract_thread.py)) uses `response_schema=DealExtraction` with Gemini's structured output mode — the model is constrained to the exact Pydantic schema at the API level, not via prompt engineering.

---

### Agent 2 — Deal Chief (Negotiation & Replies)

**Trigger:** Inbound brand deal email detected by DNA Reader, or manual trigger.
**Latency:** ~60 seconds to draft-ready.

**8-Step Pipeline:**

| Step | Action | Data Source |
|------|--------|-------------|
| 1 | Brand history lookup | `brands.findOne({domain})` → `payment_reliability`, `avg_payment_days` |
| 2 | Atlas Vector Search for similar deals | `$vectorSearch` with `RETRIEVAL_QUERY` task type, 768d cosine, top-5 |
| 3 | Skills Map preference check | `skills_map.find({confidence ≥ 0.70})` → PREFER/AVOID nodes |
| 4 | Rate benchmark from Niche Graph | `niche_graph.findOne({niche, tier, format})` → P25/P50/P75 |
| 5a | Flag generation | 7 distinct flag types: `first_time_brand`, `brand_slow_payer`, `exclusivity_too_long`, `rate_below_market`, `amount_ambiguous`, `agency_contact`, missing payment terms |
| 5b | Complexity scoring → model selection | If equity/multi-year/buyout signals detected → **Gemini 2.5 Pro**; else **Gemini 2.5 Flash** |
| 6 | **Call A** — Draft generation | Full context (voice profile + deal context + similar deals + market benchmarks) |
| 7 | **Call B** — Voice compliance evaluation | **Separate Gemini call, separate context window.** Evaluator scores voice match without knowing it's evaluating Call A. If score < 0.75, draft is regenerated with tighter constraints. |
| 8 | HITL presentation | SSE push → creator UI → Approve / Edit / Reject |

**Two-Model Voice Architecture:** Call A (generator) and Call B (evaluator) are completely independent Gemini API calls with separate context windows and separate system prompts ([voice_compliance.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/voice_compliance.py)). The evaluator uses `response_schema=VoiceComplianceResult` for structured scoring. This prevents the known failure mode where an LLM scores its own output as high-quality.

**On creator approval:** `send_gmail_reply()` is structurally callable only from explicit approval endpoints. The `ACTION_POLICY` ([action_policy.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/action_policy.py)) is **Python code, not a prompt** — email sending actions are in `ALWAYS_REQUIRE_CREATOR_APPROVAL` as an immutable set.

---

### Agent 3 — Revenue Guardian (Invoice Follow-ups)

**Trigger:** Cloud Scheduler daily at 6:30 AM IST, or manual dashboard trigger.

**Key principle:** The ranking and tone recommendation are computed entirely by MongoDB aggregation, not by Python or AI.

```javascript
// urgency_score formula — runs in $addFields (pure MongoDB arithmetic)
urgency_score = (days_overdue × 0.6) + ((1 - brand.payment_reliability) × 40)

// recommended_tone — computed by $switch in MongoDB
$switch: {
  branches: [
    { case: { $lte: ["$days_overdue", 14] }, then: "gentle" },
    { case: { $lte: ["$days_overdue", 45] }, then: "firm" }
  ],
  default: "final_notice"
}
```

**Three tone-specific system prompts:** Each tone (`gentle`, `firm`, `final_notice`) has a dedicated system prompt with distinct energy level, word count targets, and behavioral rules. The creator's voice profile controls *how* that energy is expressed — a casual creator sending a final notice still sounds like themselves.

**Per-outcome learning loop:** Every time an invoice gets paid, a MongoDB **Change Stream** ([change_streams.py](file:///d:/Development/HACKATHONS/threadcomb/backend/database/change_streams.py)) detects the update, recalculates the brand's `avg_payment_days` using a running average, and updates `payment_reliability`. The next Revenue Guardian run uses these improved scores automatically.

---

## Google Cloud ADK & Vertex AI — Production Architecture

ThreadComb uses the **Google Agent Development Kit (ADK)** for multi-agent orchestration with the **A2A (Agent-to-Agent) protocol**.

### ADK Master Orchestrator

The [orchestrator.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/orchestrator.py) implements a **two-tier routing system**:

1. **Deterministic routing table** — 20+ keyword rules that cover ~90% of creator inputs without an LLM call. `"audit"` → `dna_reader`, `"invoice"` → `revenue_guardian`, etc.
2. **Gemini Flash-Lite LLM fallback** — For ambiguous inputs, a structured JSON call routes to the correct agent with a confidence score.

The orchestrator can dispatch multiple agents simultaneously (`"run all"` → fires DNA Reader, Deal Chief, and Revenue Guardian in parallel via `asyncio.create_task()`).

### Vertex AI Dual-Mode Client

The Gemini client ([gemini_client.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/gemini_client.py)) supports **two operational modes** via a single `USE_VERTEX_AI` environment flag:

| Mode | Config | Model | Rate Limits | Use Case |
|------|--------|-------|-------------|----------|
| **AI Studio** | `USE_VERTEX_AI=false` | `gemini-2.5-flash-lite` | 15 RPM (free tier) | Development, demos |
| **Vertex AI** | `USE_VERTEX_AI=true` | `gemini-2.5-flash` | 1000+ RPM | Production deployment |

When Vertex AI is enabled, the `google.genai.Client` initialises with `vertexai=True`, `project=`, and `location=us-central1` — using Google Cloud IAM service account credentials instead of API keys. This enables:
- **Production-grade rate limits** (1000+ RPM vs 15 RPM)
- **Enterprise SLAs** and compliance
- **Automatic retry** with exponential backoff (`HttpRetryOptions` configured with 4 attempts, codes 408/429/500-504)

### Gemini Model Tiering

| Task | Model | Why |
|------|-------|-----|
| Gate classification (Stage 0) | `gemini-2.5-flash-lite` (Studio) / `gemini-2.5-flash` (Vertex) | Cheapest model for binary decisions |
| Deal extraction + draft generation | `gemini-2.5-flash` | Structured output with Pydantic schema enforcement |
| Complex deal drafts (equity/buyout) | `gemini-2.5-pro` | Multi-document reasoning for high-stakes negotiations |
| Audit Report synthesis | `gemini-2.5-pro` (fallback: Flash) | Complex multi-source synthesis with strict anti-hallucination rules |
| Voice compliance evaluation | `gemini-2.5-flash` | Structured scoring via `response_schema=VoiceComplianceResult` |
| Embeddings (index + search) | `gemini-embedding-2-preview` @ 768d | Asymmetric task typing: `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search |

---

## MongoDB Atlas — The Operational Brain

> **The Skills Map is not stored in MongoDB. The Skills Map *IS* MongoDB.**

Every agent reads from MongoDB before acting. Every outcome writes back. The database is not a passive store — it is the operational brain that makes every AI decision grounded in data, not LLM inference.

### MongoDB Features Used

| Feature | Implementation |
|---------|---------------|
| **Atlas Vector Search** | 768d cosine similarity index (`deal_embeddings_index`). Asymmetric task typing: `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search. Self-match verified = 1.0000. |
| **Aggregation Pipelines** | `urgency_score` + `recommended_tone` computed in `$addFields`/`$switch`. Revenue leakage, payment reliability, and rate gap — all computed in MongoDB, zero Python arithmetic. |
| **Change Streams** | Invoice paid → `watch_invoice_payments()` fires → brand `payment_reliability` and `avg_payment_days` auto-updated via running average. Collection-level, M0 compatible. |
| **14 Collections** | `creators`, `brands`, `deals`, `invoices`, `skills_map`, `agent_actions`, `fan_interactions`, `fan_profiles`, `response_templates`, `niche_graph`, `audit_reports`, `fan_signals`, `deal_drafts`, `invoice_followups` + `ingestion_jobs`, `ingestion_tasks`, `creator_sessions` (created at index time). |
| **Comprehensive Indexing** | 30+ indexes including compound indexes for `(creator_id, status)`, `(creator_id, initiated_at)`, `(niche, follower_tier, content_format)`. |

### Data Classification on Every Write

All MongoDB writes go through a single chokepoint: [mongodb_writer.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/mongodb_writer.py). Every document automatically receives:

```python
{
    "data_classification": {
        "tier": "personal_identifiable",  # or "anonymisable" or "aggregate"
        "deletion_policy": "on_request_30d",
        "anonymisation_eligible": true,
        "export_eligible": true,
        "classified_at": "2026-06-10T..."
    }
}
```

No `collection.insert_one()` call exists anywhere outside this module.

---

## The Skills Map — ThreadComb's Compounding Asset

The Skills Map is a living knowledge graph in MongoDB that accumulates with every email processed.

**Individual creator data (private):**
- `creators.voice_profile_brand` — how they write to brands (formality, Hindi ratio, openers/closers)
- `deals.*` — every deal, outcome, and 768d embedding vector
- `skills_map.*` — inferred preferences (PREFER/AVOID) with evidence counts and decay rates
- `brands.payment_intelligence` — per-brand payment behaviour

**Anonymised niche intelligence (shared via Niche Graph):**
- `niche_graph.*` — P25/P50/P75 rates by niche × follower_tier × content_format
- Confidence weight: 0.40 (single source) → 0.85 (3+ corroborating sources)

```python
# Skills Map preference node example
{
    "creator_id": "...",
    "type": "preference",
    "name": "prefers_beauty_brands",
    "preference": {"polarity": "PREFER", "value": "beauty", "strength": 0.63},
    "evidence": {"count": 7, "confidence": 0.70, "decay_rate": 0.002}
}
# confidence = min(count / 10, 1.0) — decays if not reinforced
```

**Switching cost:** A creator with 12 months of Skills Map history would lose all accumulated intelligence by switching. The moat is not the technology — it's the compounding operational knowledge.

---

## The Niche Corpus — Current State & Roadmap

### What Exists Today

The **Corpus Ingestion Pipeline** ([ingest.py](file:///d:/Development/HACKATHONS/threadcomb/backend/corpus/ingest.py)) is a fully functional 726-line CLI tool that:

1. **Discovers** documents across 5 source types: `industry_reports`, `contract_templates`, `public_media_kits`, `brand_signals`, `disclosure_data`
2. **Extracts** structured signals via Gemini 2.5 Flash (rate benchmarks, brand signals, contract clauses)
3. **Cross-validates** across sources — computes `corroboration_score` based on how many distinct source types confirm a data point
4. **Writes** validated `niche_graph` nodes and brand signals to MongoDB (idempotent — re-running produces identical output)
5. **Detects outliers** — values >2σ from mean are flagged for human review

Supported formats: PDF (via pdfplumber), TXT, MD, CSV, JSON.

### Current Limitation

**High-quality, reliable market data takes time to collect and curate.** The Niche Graph is being actively populated with ASCI reports, industry analyses, and anonymised market rates. As this corpus grows, it will provide an **extraordinary compounding moat** — ThreadComb will be able to benchmark any creator's rates against real market data from thousands of data points.

**Until the Niche Graph is fully populated, ThreadComb relies on the creator's individual Skills Map.** The system uses the creator's own deal history, closure patterns, and inferred preferences (PREFER/AVOID) to guide and benchmark. This ensures that from Day 1, every AI decision is grounded in the creator's actual operational reality, not hallucinated industry averages.

---

## Architecture

```
Creator (Browser)
      │
      │  Next.js 16 + React 19 (App Router, Tailwind CSS, shadcn/ui)
      │  Server-Sent Events for real-time agent progress streaming
      │  Zustand state management, Recharts visualisations
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (Cloud Run)                │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │          Google ADK Master Orchestrator           │  │
│  │    Deterministic routing + Gemini LLM fallback   │  │
│  │              A2A Protocol routing                 │  │
│  └──────────┬──────────┬──────────┬─────────────────┘  │
│             │          │          │                     │
│      ┌──────▼──┐ ┌─────▼────┐ ┌──▼───────────┐        │
│      │  DNA    │ │  Deal    │ │  Revenue     │        │
│      │ Reader  │ │  Chief   │ │  Guardian    │        │
│      └──────┬──┘ └─────┬────┘ └──┬───────────┘        │
│             │          │          │                     │
│  ┌──────────▼──────────▼──────────▼──────────────────┐ │
│  │    ACTION_POLICY — Python code, NOT a prompt       │ │
│  │    ALWAYS_REQUIRE_CREATOR_APPROVAL = {             │ │
│  │        SEND_BRAND_DEAL_EMAIL,                      │ │
│  │        SEND_INVOICE_FOLLOWUP,                      │ │
│  │        SEND_FAN_REPLY                              │ │
│  │    }                                               │ │
│  └────────────────────────────────────────────────────┘ │
│                                                        │
│  Services: SSE Manager, Email Sanitiser, Gmail Auth,   │
│  Voice Profiler, PDF Generator, OIDC Auth              │
└────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                  MongoDB Atlas (M0)                      │
│  ┌──────────────┐  ┌──────────────────────────────┐     │
│  │ 14+ Colls    │  │ Atlas Vector Search           │     │
│  │ 30+ Indexes  │  │ 768d cosine, deal_embeddings  │     │
│  └──────────────┘  └──────────────────────────────┘     │
│  ┌──────────────┐  ┌──────────────────────────────┐     │
│  │ Aggregation  │  │ Change Streams               │     │
│  │ Pipelines    │  │ invoice paid → brand update   │     │
│  └──────────────┘  └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
      │
      ├── Gmail API v1 (Push via Pub/Sub + Read + Send)
      ├── Google Cloud Tasks (Async extraction queue + DLQ)
      ├── Google Cloud Pub/Sub (Gmail push webhook notifications)
      ├── Google Cloud Scheduler (Daily Guardian, Weekly Synthesis, Gmail Watch Renewal)
      ├── Google Cloud Storage (Audit Report PDFs)
      ├── Google Cloud IAM + Secret Manager (OAuth tokens, service accounts)
      └── Vertex AI (Production Gemini access via google.genai.Client)
```

---

## Key Design Decisions

### 1. ACTION_POLICY is Python code, not a prompt

```python
# backend/services/action_policy.py — line 32
ALWAYS_REQUIRE_CREATOR_APPROVAL = {
    ActionType.SEND_BRAND_DEAL_EMAIL,
    ActionType.SEND_INVOICE_FOLLOWUP,
    ActionType.SEND_FAN_REPLY,
}
```

`send_gmail_reply()` is structurally callable only from explicit approval endpoints. You cannot accidentally add an auto-send code path — the architecture prevents it.

### 2. Raw email text never persists

Email body text is processed in-memory by [email_sanitiser.py](file:///d:/Development/HACKATHONS/threadcomb/backend/services/email_sanitiser.py) and discarded after extraction. Only structured signals are stored. The one exception — Cloud Tasks payload transit — is documented as `NAMED_EXCEPTIONS["CLOUD_TASKS_SANITISED_TEXT_TRANSIT"]` in the action policy.

### 3. Financial accuracy via amount_ambiguity_flag

If a deal amount is informal ("50 hazaar", "let's discuss", "competitive budget"), `amount_ambiguity_flag=true` and ALL amount fields are forced to `None`. The Audit Report says "value unknown — amount not stated" rather than hallucinating. This is enforced at the Pydantic schema level — the model cannot output amounts when the flag is set.

### 4. HITL as a first-class architecture

Every agent action is logged as an immutable document in `agent_actions`. Low-confidence extractions (below 0.60) go to a review queue rather than being written to `deals`. The creator can see every decision, its confidence score, and why it was made.

### 5. DLQ (Dead Letter Queue) for extraction resilience

Failed extractions are retried 3 times with escalating backoff. After max retries, threads are quarantined as `dead_letter` in `ingestion_tasks` rather than silently dropped. The audit pipeline still triggers once all threads are resolved (completed + errored + low-confidence = queued).

---

## Privacy & Compliance (DPDP Act 2023)

- **Data classification on every write:** All MongoDB writes include `data_classification.tier` and `deletion_policy` via the `write_with_classification()` chokepoint.
- **Right to erasure:** `DELETE /api/settings/delete-account` purges all `personal_identifiable` documents across all collections.
- **Data portability:** `GET /api/settings/export` returns the complete Skills Map as JSON.
- **PII redaction:** Phone numbers (Indian +91 and international formats) and addresses are regex-redacted in the sanitiser before any API call.
- **Structural HITL:** No email is ever sent without explicit creator approval — this is enforced by Python code (`ACTION_POLICY`), not by a prompt.

---

## Tech Stack

### AI & Orchestration

| Component | Technology | Details |
|-----------|-----------|---------|
| Agent Orchestration | **Google Cloud ADK + A2A** | Deterministic routing table + Gemini LLM fallback for ambiguous inputs |
| Gate Classifier | **Gemini 2.5 Flash-Lite** | Binary deal-signal classification, cheapest model for high-volume screening |
| Extraction + Drafts | **Gemini 2.5 Flash** | `response_schema` structured output with Pydantic v2 schemas |
| Complex Synthesis | **Gemini 2.5 Pro** | Audit Report generation with strict anti-hallucination rules, Pro→Flash fallback |
| Embeddings | **gemini-embedding-2-preview @ 768d** | Asymmetric task typing (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY), manual L2 normalisation |
| Production API | **Vertex AI** | `google.genai.Client(vertexai=True)` with Cloud IAM, 1000+ RPM, enterprise SLAs |

### Backend Infrastructure

| Component | Technology | Details |
|-----------|-----------|---------|
| API Framework | **FastAPI + Python 3.11** | Fully async, Pydantic v2 schema enforcement on all endpoints |
| Schema Validation | **Pydantic v2** | 12 model files, 40+ schemas including DealExtraction, VoiceComplianceResult |
| Real-time Streaming | **Server-Sent Events (SSE)** | In-memory pub/sub with 30s heartbeat, auto-reconnect on frontend |
| Hosting | **Google Cloud Run** | Always-warm for Gmail Pub/Sub webhooks |
| Task Queue | **Google Cloud Tasks** | Rate-limited extraction with automatic retry and DLQ |
| Push Notifications | **Google Cloud Pub/Sub** | Gmail push webhooks — new email → agent fires in 30s |
| Scheduling | **Google Cloud Scheduler** | Daily Guardian (6:30 AM IST), weekly synthesis (Sunday 2 AM IST), Gmail watch renewal (every 6 days) |
| PDF Generation | **reportlab** | Audit Report PDFs |
| PDF Parsing | **pdfplumber** | Contract clause extraction for corpus ingestion |
| Storage | **Google Cloud Storage** | Audit Report PDF hosting |
| Auth | **Google OAuth 2.0 + OIDC** | Creator login + Cloud Scheduler endpoint verification |

### Database — MongoDB Atlas

| Feature | Usage |
|---------|-------|
| Document Store | 14+ collections, flexible nested documents, Motor async driver |
| Atlas Vector Search | `deal_embeddings_index`: 768d cosine similarity, creator_id + extraction_confidence filters |
| Aggregation Pipelines | Urgency scoring (`$addFields` + `$switch`), revenue leakage, payment reliability, rate gap |
| Change Streams | Invoice paid → brand payment intelligence auto-update (collection-level, M0 compatible) |
| Comprehensive Indexes | 30+ indexes including compound indexes for query-critical paths |

### Frontend

| Component | Technology | Details |
|-----------|-----------|---------|
| Framework | **Next.js 16 + React 19** | App Router, TypeScript |
| Styling | **Tailwind CSS 3.4** | Custom design system |
| Component Library | **shadcn/ui (Radix UI)** | 25+ Radix primitives (Dialog, Dropdown, Tabs, Tooltip, etc.) |
| State Management | **Zustand** | Lightweight client state |
| Visualisations | **Recharts** | Dashboard data visualisations |
| Typography | **Outfit + Figtree + Space Mono** | Google Fonts with CSS variable system |
| Analytics | **Vercel Analytics + Speed Insights** | Performance monitoring |
| Notifications | **Sonner** | Rich toast notifications |
| Hosting | **Vercel** | Edge deployment |

---

## Project Structure

```
threadcomb/
├── backend/
│   ├── server.py                    # FastAPI entry — mounts 14 routers, starts Change Streams
│   ├── config.py                    # Settings: USE_VERTEX_AI, GEMINI_TIER, rate limiting
│   │
│   ├── models/                      # 12 Pydantic v2 schema files
│   │   ├── deal.py                  # DealExtraction (40+ fields), Brand, Invoice, SkillsMapNode
│   │   ├── draft.py                 # DraftResult, DraftFlag, VoiceComplianceResult
│   │   ├── audit.py                 # SynthesisContext, SynthesisReport, AuditFinding
│   │   ├── creator.py               # Creator, VoiceProfileBrand, Onboarding schemas
│   │   ├── invoice.py               # InvoiceFollowUpDraft, BatchFollowUpResult
│   │   ├── ingestion.py             # IngestionJob, SanitisedThread, GateClassificationResult
│   │   ├── corpus.py                # PublicDataExtraction for corpus pipeline
│   │   ├── niche_graph.py           # NicheGraphNode
│   │   └── common.py               # DataClassification, AgentActionType, ActionResult
│   │
│   ├── services/                    # 23 service modules
│   │   ├── orchestrator.py          # ADK Master Orchestrator (deterministic + LLM routing)
│   │   ├── deal_chief.py            # 8-step Deal Chief pipeline
│   │   ├── deal_search.py           # Atlas Vector Search (RETRIEVAL_QUERY)
│   │   ├── revenue_guardian.py      # Urgency aggregation + follow-up drafts
│   │   ├── ingestion_gate.py        # Stage 0 Flash-Lite gate + fan signal detection
│   │   ├── email_sanitiser.py       # In-memory PII redaction, MIME parsing
│   │   ├── gemini_client.py         # Dual-mode: AI Studio / Vertex AI client
│   │   ├── voice_compliance.py      # Call B — independent voice evaluator
│   │   ├── voice_profiler.py        # Brand voice extraction from outbound emails
│   │   ├── audit_pipelines.py       # 3 MongoDB aggregation pipelines
│   │   ├── audit_generator.py       # Gemini Pro synthesis (Pro→Flash fallback)
│   │   ├── action_policy.py         # ACTION_POLICY — Python code, not a prompt
│   │   ├── mongodb_writer.py        # write_with_classification() — all writes chokepoint
│   │   ├── sse_manager.py           # In-memory SSE pub/sub with heartbeat
│   │   ├── gmail_fetcher.py         # Gmail API thread fetching
│   │   ├── gmail_sender.py          # Gmail reply sender (approval endpoints only)
│   │   ├── gmail_auth.py            # OAuth credential management
│   │   ├── gmail_watch.py           # Gmail push notification registration
│   │   ├── pdf_generator.py         # reportlab PDF + GCS upload
│   │   ├── calendar_service.py      # Google Calendar follow-up events
│   │   ├── ingestion_queue.py       # Cloud Tasks queue management
│   │   └── oidc_auth.py             # Cloud Scheduler OIDC verification
│   │
│   ├── workers/
│   │   ├── extract_thread.py        # Full extraction worker (585 lines) with DLQ
│   │   └── process_thread.py        # Cloud Tasks HTTP endpoint
│   │
│   ├── routers/                     # 14 API routers
│   │   ├── ingestion.py             # Start audit, status, direct triggers
│   │   ├── audit.py                 # Generate + fetch Audit Reports
│   │   ├── deals.py                 # Deal inbox, draft generation, approve/reject
│   │   ├── guardian.py              # Revenue Guardian trigger, approve follow-ups
│   │   ├── orchestrator.py          # SSE streaming natural language → agent routing
│   │   ├── hitl.py                  # Low-confidence review queue
│   │   ├── settings.py              # Export Skills Map, delete account
│   │   ├── auth.py                  # Google OAuth login/callback
│   │   ├── onboarding.py            # 4-step creator onboarding
│   │   ├── internal.py              # Cloud Scheduler: watches, synthesis, overdue check
│   │   └── webhooks.py              # Gmail Pub/Sub push handler
│   │
│   ├── database/
│   │   ├── mongodb.py               # Motor singleton, 30+ indexes, collection management
│   │   ├── change_streams.py        # Invoice paid → brand intelligence update
│   │   ├── seed.py, seed_demo.py    # Niche graph seed + hackathon demo data
│   │   └── migrate.py               # Schema migrations
│   │
│   └── corpus/
│       └── ingest.py                # 726-line CLI: extract → cross-validate → write
│
└── frontend/
    ├── src/app/
    │   ├── dashboard/               # Main dashboard with 8 sub-pages
    │   │   ├── audit/               # Audit Report viewer
    │   │   ├── deals/               # Deal inbox + draft approval UI
    │   │   ├── hitl/                # HITL review queue
    │   │   ├── activity/            # Agent action audit log
    │   │   ├── invoices/            # Invoice tracking
    │   │   ├── reports/             # Report history
    │   │   └── settings/            # Account settings
    │   ├── onboarding/              # 4-step creator setup
    │   └── login/                   # Google OAuth login
    ├── src/components/
    │   ├── orchestrator/            # Natural language command bar
    │   ├── ingestion/               # Real-time ingestion progress
    │   └── ui/                      # shadcn/ui component library
    └── src/hooks/
        └── useIngestionStatus.ts    # SSE hook for real-time updates
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+, Node.js 18+
- MongoDB Atlas account (free M0 tier works)
- Google Cloud project with billing enabled
- Gemini API key (from [AI Studio](https://aistudio.google.com)) or Vertex AI service account

### 1. Backend Setup

```bash
git clone https://github.com/YOUR_USERNAME/threadcomb.git
cd threadcomb/backend

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.example .env          # Fill in MONGODB_URI, GEMINI_API_KEY, etc.
```

### 2. Database Initialisation

```bash
# Creates all collections, indexes, and seeds niche_graph baseline data
python database/run_seed.py
```

> **Note:** Create the Atlas Vector Search index manually in the Atlas UI:
> Collection: `deals` | Field: `embedding_vector` | Dimensions: 768 | Similarity: cosine | Index name: `deal_embeddings_index`

### 3. Corpus Ingestion (Optional)

```bash
python corpus/ingest.py --folder ../corpus/data/ --dry-run   # Preview
python corpus/ingest.py --folder ../corpus/data/              # Write to MongoDB
```

### 4. Start the Application

```bash
# Backend
cd backend
uvicorn server:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
cp .env.local.example .env.local   # Set NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
npm run dev
```

### 5. Enable Vertex AI for Production

```bash
# In backend/.env
USE_VERTEX_AI=true
GOOGLE_CLOUD_PROJECT=your-project-id
# Ensure service account has Vertex AI User role
```

---

## API Endpoints

### Core Agent Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingestion/start` | Start full Gmail scan (DNA Reader) |
| GET | `/api/sse/ingestion/{creator_id}` | SSE stream for real-time ingestion progress |
| POST | `/api/audit/generate/{creator_id}` | Generate Audit Report |
| GET | `/api/deals/` | Inbound deals needing attention |
| POST | `/api/deals/{deal_id}/draft` | Trigger Deal Chief pipeline |
| POST | `/api/deals/{deal_id}/approve` | Approve and send reply |
| POST | `/api/guardian/run` | Trigger Revenue Guardian |
| POST | `/api/guardian/approve-batch` | Approve multiple follow-ups |
| GET | `/api/orchestrate` | SSE: natural language → agent routing |

### Internal (Cloud Scheduler)

| Endpoint | Schedule | Action |
|----------|----------|--------|
| `/internal/renew-gmail-watches` | Every 6 days | Renew Gmail push notification watches |
| `/internal/run-pattern-synthesis` | Sunday 2 AM IST | Re-run Skills Map synthesis |
| `/internal/check-overdue-invoices` | Daily 6:30 AM IST | Update days_overdue, run Revenue Guardian |

---

## What's Next

**Phase 2:**
- **Fan Management Agent** — Instagram DM + YouTube comment classification
- **Fivetran connectors** — YouTube Studio analytics + Stripe → MongoDB Atlas
- **Graphiti + FalkorDB** — Temporal knowledge graph for deeper Skills Map reasoning
- **Arize Phoenix** — LLM observability and agent quality tracking
- **Redis Pub/Sub** — Replace in-memory SSE for horizontal scaling

---

## Team

| Name | Role | Contact |
|------|------|---------|
| Mohd Danish | Founder & Builder | [LinkedIn](https://www.linkedin.com/in/mohd-danish-007-dev/) [GitHub](https://github.com/Danish007Dev/) |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built for the MongoDB Partner Track.**

Powered by MongoDB Atlas, Google Cloud ADK, Vertex AI, Gemini 2.5, and the collective operational chaos of 3 million Indian content creators who deserve better.

**ThreadComb — threadcomb.com**

*Not a tool that helps you do the work. A system that does the work.*

</div>