# ThreadComb Corpus Data

Place downloaded public-source files in the correct subfolder. The ingestion
pipeline determines `source_type` from the folder name — anything outside
these folders is skipped.

## Folder → Source Type Mapping

| Folder                  | source_type          | Examples                                              |
|-------------------------|----------------------|-------------------------------------------------------|
| `industry_reports/`     | `industry_report`    | ASCI annual report, FICCI-EY, RedSeer, Kalaari       |
| `contract_templates/`   | `contract_template`  | SpotDraft, Leegality influencer templates             |
| `public_media_kits/`    | `public_media_kit`   | Creator media kit PDFs publicly shared by creators    |
| `brand_signals/`        | `brand_signal`        | YouTube description CSV exports, ASCI brand lists     |
| `disclosure_data/`      | `disclosure_data`     | Instagram #ad / paid-partnership disclosures          |

## Supported file types

`.pdf`, `.txt`, `.md`, `.csv`, `.json`

## Running the pipeline

```bash
# Dry run — see what would be written without writing anything
python backend/corpus/ingest.py --folder ./corpus/data/ --dry-run

# Full run — writes to MongoDB
python backend/corpus/ingest.py --folder ./corpus/data/

# Filter to a single niche
python backend/corpus/ingest.py --folder ./corpus/data/ --niche beauty
```

The pipeline is **idempotent**. Running it twice on the same folder produces
identical MongoDB state (upserts, not inserts).

## Confidence weight scale

`confidence_weight` quantifies how trustworthy a benchmark is.
Derived deterministically from `corroboration_score = distinct_source_types / 3`
via the formula `confidence_weight = 0.40 + (corroboration_score × 0.45)`.

| Source types confirming | corroboration_score | confidence_weight |
|-------------------------|---------------------|-------------------|
| 1                       | 0.333               | **0.55**           |
| 2                       | 0.667               | **0.70**           |
| 3+                      | 1.000               | **0.85** (max for pre-training) |
| Real creator data       | —                   | **0.90** (set by ingestion agent, not this pipeline) |
| Human-reviewed          | —                   | **1.00**           |

The defined **minimum is 0.40**. Anything below is invalid placeholder data
and is deleted by `backend/database/migrate.py`.

## What flows where

- `rate_benchmarks` from extractions → **niche_graph** collection (after cross-validation).
- `brand_signals` from extractions  → **brands** collection (one document per brand,
  aggregated across all sources).
- `clauses` from extractions       → currently extracted but **not yet written** —
  goes to `corpus_clauses` in a future session.

## Files in this folder are NOT committed

PDF / CSV / TXT data files are gitignored. Only the folder structure
(`.gitkeep` files) and this README are versioned.
